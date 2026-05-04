"""
core/tools/repo_edit_agent_bridge.py

Code Chain v0.6 forced routing bridge.

Purpose:
- Detect explicit repository/code edit tasks before the LLM can finish with only
  a natural-language answer.
- Convert the task into a repo_edit_tool payload.
- Execute repo_edit_tool directly.
- Return an observable result that shows whether the tool was called.

v0.6.1 fix:
- Accept CodeEditIntent.status == "ready" as executable.
- Do not block ready controlled_replace intents.
- Preserve payload/intention details in the result for tracing.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping


TOOL_NAME = "repo_edit_tool"


_EDIT_KEYWORDS = (
    "modify",
    "edit",
    "change",
    "replace",
    "update",
    "refactor",
    "rewrite",
    "add comment",
    "add a comment",
    "rename",
    "fix",
    "修",
    "修改",
    "變更",
    "替換",
    "更改",
    "更新",
    "重構",
    "加入註解",
    "加註解",
)


_FILE_HINTS = (
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".bat",
    ".ps1",
    ".sh",
    "workspace/",
    "workspace\\",
    "core/",
    "core\\",
    "demos/",
    "demos\\",
    "docs/",
    "docs\\",
)


_READY_STATUSES = {"ok", "ready", "approved", "apply", "accepted", "executable"}
_BLOCKED_STATUSES = {"blocked", "failed", "error", "rejected", "denied"}


def _to_dict(value: Any) -> dict[str, Any]:
    """Best-effort conversion for dataclasses / mapping / simple objects."""
    if value is None:
        return {}

    if isinstance(value, dict):
        return dict(value)

    if is_dataclass(value):
        return asdict(value)

    if isinstance(value, Mapping):
        return dict(value)

    result: dict[str, Any] = {}
    for name in (
        "status",
        "reason",
        "file_path",
        "target_path",
        "path",
        "old_text",
        "new_text",
        "old_line",
        "new_line",
        "mode",
        "operation",
        "type",
        "instruction",
        "task_text",
    ):
        if hasattr(value, name):
            result[name] = getattr(value, name)
    return result


def _normalize_task_text(task_text: Any) -> str:
    if task_text is None:
        return ""
    return str(task_text).strip()


def _status_text(payload: Mapping[str, Any] | None) -> str:
    if not isinstance(payload, Mapping):
        return ""
    return str(payload.get("status") or "").strip().lower()


def _is_ready_status(status: str) -> bool:
    text = str(status or "").strip().lower()
    return (not text) or text in _READY_STATUSES


def _is_blocked_status(status: str) -> bool:
    text = str(status or "").strip().lower()
    return text in _BLOCKED_STATUSES


def looks_like_repo_edit_task(task_text: str) -> bool:
    """
    Lightweight deterministic gate.

    This is not the source of truth. The real source of truth is
    parse_code_edit_intent(). This gate only avoids unnecessary parser calls
    for obviously unrelated tasks.
    """
    text = _normalize_task_text(task_text)
    if not text:
        return False

    lowered = text.lower()
    has_edit_word = any(word in lowered for word in _EDIT_KEYWORDS)
    has_file_hint = any(hint.lower() in lowered for hint in _FILE_HINTS)

    return has_edit_word and has_file_hint


def _load_repo_edit_components() -> tuple[Any, Any, Any]:
    """
    Import lazily so this bridge does not break startup if repo-edit modules are
    unavailable in minimal runtimes.
    """
    from core.repo_sandbox.intent import build_repo_edit_payload, parse_code_edit_intent
    from core.tools.repo_edit_tool import repo_edit_tool

    return parse_code_edit_intent, build_repo_edit_payload, repo_edit_tool


def build_forced_repo_edit_payload(task_text: str) -> dict[str, Any]:
    """
    Parse task_text into the payload expected by repo_edit_tool.

    Returns:
    - ok: bool
    - payload: dict | None
    - intent: dict
    - reason: str
    """
    text = _normalize_task_text(task_text)
    if not text:
        return {
            "ok": False,
            "payload": None,
            "intent": {},
            "reason": "empty task text",
        }

    try:
        parse_code_edit_intent, build_repo_edit_payload, _repo_edit_tool = _load_repo_edit_components()
    except Exception as exc:
        return {
            "ok": False,
            "payload": None,
            "intent": {},
            "reason": f"repo edit components unavailable: {exc}",
        }

    try:
        intent_obj = parse_code_edit_intent(text)
        intent = _to_dict(intent_obj)
    except Exception as exc:
        return {
            "ok": False,
            "payload": None,
            "intent": {},
            "reason": f"intent parse failed: {exc}",
        }

    intent_status = _status_text(intent)
    if _is_blocked_status(intent_status):
        return {
            "ok": False,
            "payload": None,
            "intent": intent,
            "reason": str(intent.get("reason") or f"intent status is {intent_status}"),
        }

    if not _is_ready_status(intent_status):
        return {
            "ok": False,
            "payload": None,
            "intent": intent,
            "reason": str(intent.get("reason") or f"intent status is {intent_status}"),
        }

    try:
        payload_obj = build_repo_edit_payload(intent_obj)
        payload = _to_dict(payload_obj)
    except Exception as exc:
        return {
            "ok": False,
            "payload": None,
            "intent": intent,
            "reason": f"payload build failed: {exc}",
        }

    if not payload:
        return {
            "ok": False,
            "payload": None,
            "intent": intent,
            "reason": "empty repo edit payload",
        }

    payload_status = _status_text(payload)
    if _is_blocked_status(payload_status):
        return {
            "ok": False,
            "payload": payload,
            "intent": intent,
            "reason": str(payload.get("reason") or f"payload status is {payload_status}"),
        }

    # Force v0.6 executable shape even if downstream aliases differ.
    payload["status"] = "ready"
    payload["mode"] = "controlled_replace"
    payload["operation"] = "controlled_replace"
    payload["type"] = "controlled_replace"
    payload["controlled_replace"] = True
    payload["controlled_replace_ready"] = True
    payload["code_chain_version"] = "v0.6"

    return {
        "ok": True,
        "payload": payload,
        "intent": intent,
        "reason": "forced repo edit payload built",
    }


def run_repo_edit_decision(
    task_text: str,
    *,
    repo_root: str = ".",
    force: bool = False,
) -> dict[str, Any]:
    """
    Main entrypoint for agent_loop / planner / scheduler.

    Behavior:
    - If task does not look like a repo edit and force=False, return skipped.
    - If parser produces a valid CodeEditIntent, execute repo_edit_tool.
    - Always returns a dict; never raises into the agent loop/scheduler.
    """
    text = _normalize_task_text(task_text)

    if not force and not looks_like_repo_edit_task(text):
        return {
            "handled": False,
            "forced_route": False,
            "tool_name": TOOL_NAME,
            "status": "skipped",
            "reason": "task does not look like an explicit repo edit task",
            "task_text": text,
        }

    payload_result = build_forced_repo_edit_payload(text)
    if not payload_result.get("ok"):
        return {
            "handled": True,
            "forced_route": True,
            "tool_name": TOOL_NAME,
            "status": "blocked",
            "reason": payload_result.get("reason", "unable to build repo edit payload"),
            "payload": payload_result.get("payload"),
            "intent": payload_result.get("intent", {}),
            "task_text": text,
        }

    payload = dict(payload_result["payload"] or {})
    payload.setdefault("task_text", text)
    payload.setdefault("instruction", text)

    try:
        _parse_code_edit_intent, _build_repo_edit_payload, repo_edit_tool = _load_repo_edit_components()
    except Exception as exc:
        return {
            "handled": True,
            "forced_route": True,
            "tool_name": TOOL_NAME,
            "status": "blocked",
            "reason": f"repo_edit_tool unavailable: {exc}",
            "payload": payload,
            "intent": payload_result.get("intent", {}),
            "task_text": text,
        }

    try:
        tool_result = repo_edit_tool(payload, repo_root=repo_root)
    except TypeError:
        try:
            tool_result = repo_edit_tool(payload)
        except Exception as exc:
            return {
                "handled": True,
                "forced_route": True,
                "tool_name": TOOL_NAME,
                "status": "failed",
                "reason": f"repo_edit_tool failed: {exc}",
                "payload": payload,
                "intent": payload_result.get("intent", {}),
                "task_text": text,
            }
    except Exception as exc:
        return {
            "handled": True,
            "forced_route": True,
            "tool_name": TOOL_NAME,
            "status": "failed",
            "reason": f"repo_edit_tool failed: {exc}",
            "payload": payload,
            "intent": payload_result.get("intent", {}),
            "task_text": text,
        }

    result = _to_dict(tool_result)
    status = str(result.get("status") or result.get("state") or "").strip().lower()
    ok = bool(
        result.get("ok")
        or result.get("success")
        or status in {"ok", "done", "success", "finished", "applied", "ready"}
    )

    if status in _BLOCKED_STATUSES:
        ok = False

    return {
        "handled": True,
        "forced_route": True,
        "tool_name": TOOL_NAME,
        "status": "ok" if ok else (status or "failed"),
        "reason": "repo_edit_tool called by forced routing",
        "payload": payload,
        "intent": payload_result.get("intent", {}),
        "tool_result": result,
        "task_text": text,
    }


def force_repo_edit_route(task_text: str, *, repo_root: str = ".") -> dict[str, Any]:
    """Explicit forced route helper for tests or direct calls."""
    return run_repo_edit_decision(task_text, repo_root=repo_root, force=True)


def route_repo_edit_if_needed(task_text: str, *, repo_root: str = ".") -> dict[str, Any]:
    """Compatibility alias."""
    return run_repo_edit_decision(task_text, repo_root=repo_root, force=False)


def decide_repo_edit_route(task_text: str, *, repo_root: str = ".") -> dict[str, Any]:
    """Compatibility alias."""
    return run_repo_edit_decision(task_text, repo_root=repo_root, force=False)


__all__ = [
    "TOOL_NAME",
    "looks_like_repo_edit_task",
    "build_forced_repo_edit_payload",
    "run_repo_edit_decision",
    "force_repo_edit_route",
    "route_repo_edit_if_needed",
    "decide_repo_edit_route",
]
