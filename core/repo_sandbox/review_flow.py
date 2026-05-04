"""Execution flow for natural-language repo edit tasks.

Code Chain v0.6 AUTO-APPLY REVIEW FLOW

Purpose:
- Keep the public function name run_code_edit_review_task() for compatibility.
- Do not stop at pending review for safe single-file workspace controlled_replace.
- Parse intent -> build repo-edit payload -> execute repo edit directly.
- Preserve decide_review() for older/manual review commands.

Safety boundary for auto-apply:
- Only CodeEditIntent(status="ready") is allowed.
- Only workspace/... paths are allowed by intent.py.
- Only controlled_replace mode is allowed.
- Actual write/backup/verification responsibility remains in repo_sandbox.tool /
  repo_edit_tool / controlled edit layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from core.repo_sandbox.intent import build_repo_edit_payload, parse_code_edit_intent
except Exception:  # pragma: no cover
    build_repo_edit_payload = None  # type: ignore[assignment]
    parse_code_edit_intent = None  # type: ignore[assignment]

try:
    from core.repo_sandbox.tool import run_repo_edit
except Exception:  # pragma: no cover
    run_repo_edit = None  # type: ignore[assignment]

try:
    from core.repo_sandbox.task_bridge import run_code_edit_task
except Exception:  # pragma: no cover
    run_code_edit_task = None  # type: ignore[assignment]

try:
    from core.repo_sandbox.review import apply_review, reject_review
except Exception:  # pragma: no cover
    apply_review = None  # type: ignore[assignment]
    reject_review = None  # type: ignore[assignment]


_READY_STATUSES = {"ready", "ok", "approved", "accepted", "apply", "executable"}
_ALLOWED_MODES = {"controlled_replace"}


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}

    if isinstance(value, dict):
        return dict(value)

    try:
        from dataclasses import asdict, is_dataclass

        if is_dataclass(value):
            return asdict(value)
    except Exception:
        pass

    result: dict[str, Any] = {}
    for key in (
        "status",
        "reason",
        "file_path",
        "path",
        "target_path",
        "mode",
        "operation",
        "type",
        "old_text",
        "new_text",
        "old_line",
        "new_line",
        "instruction",
    ):
        if hasattr(value, key):
            result[key] = getattr(value, key)

    return result


def _looks_auto_apply_safe(intent: Any, payload: dict[str, Any]) -> tuple[bool, str]:
    intent_payload = _to_dict(intent)
    status = str(intent_payload.get("status") or payload.get("status") or "").strip().lower()
    mode = str(
        intent_payload.get("mode")
        or payload.get("mode")
        or payload.get("operation")
        or payload.get("type")
        or ""
    ).strip().lower()

    file_path = str(
        intent_payload.get("file_path")
        or payload.get("file_path")
        or payload.get("target_path")
        or payload.get("path")
        or ""
    ).replace("\\", "/").strip()

    old_line = str(
        intent_payload.get("old_line")
        or intent_payload.get("old_text")
        or payload.get("old_line")
        or payload.get("old_text")
        or ""
    )
    new_line = str(
        intent_payload.get("new_line")
        or intent_payload.get("new_text")
        or payload.get("new_line")
        or payload.get("new_text")
        or ""
    )

    if status not in _READY_STATUSES:
        return False, f"intent status is not ready: {status or 'unknown'}"

    if mode not in _ALLOWED_MODES:
        return False, f"mode is not controlled_replace: {mode or 'unknown'}"

    if not file_path.startswith("workspace/"):
        return False, "only workspace/ paths are allowed for auto apply"

    if not old_line.strip():
        return False, "old_line/old_text is empty"

    if not new_line.strip():
        return False, "new_line/new_text is empty"

    return True, "safe single-file workspace controlled_replace auto apply"


def _build_auto_apply_payload(task_text: str) -> dict[str, Any]:
    if parse_code_edit_intent is None or build_repo_edit_payload is None:
        return {
            "ok": False,
            "status": "error",
            "reason": "intent parser is unavailable",
        }

    intent = parse_code_edit_intent(task_text)
    intent_payload = _to_dict(intent)

    try:
        payload = build_repo_edit_payload(intent)
    except Exception as exc:
        return {
            "ok": False,
            "status": "error",
            "reason": f"build_repo_edit_payload failed: {exc}",
            "intent": intent_payload,
        }

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "status": "error",
            "reason": "build_repo_edit_payload returned non-dict",
            "intent": intent_payload,
            "payload": payload,
        }

    safe, reason = _looks_auto_apply_safe(intent, payload)
    if not safe:
        return {
            "ok": False,
            "status": "blocked",
            "reason": reason,
            "intent": intent_payload,
            "payload": payload,
        }

    payload["status"] = "ready"
    payload["mode"] = "controlled_replace"
    payload["operation"] = "controlled_replace"
    payload["type"] = "controlled_replace"
    payload["controlled_replace"] = True
    payload["controlled_replace_ready"] = True
    payload["code_chain_version"] = "v0.6"
    payload.setdefault("task_text", task_text)
    payload.setdefault("instruction", task_text)

    return {
        "ok": True,
        "status": "ready",
        "reason": reason,
        "intent": intent_payload,
        "payload": payload,
    }


def run_code_edit_review_task(task_text: str, *, repo_root: str | Path = ".") -> dict[str, Any]:
    """Run a safe natural-language repo edit and auto-apply it.

    Compatibility note:
    The function name still says "review" because other modules import it.
    In v0.6 auto-apply mode, this function does not create a pending review.
    """

    text = str(task_text or "").strip()
    if not text:
        return {
            "status": "blocked",
            "reason": "empty task text",
            "auto_applied": False,
            "review_skipped": True,
        }

    prepared = _build_auto_apply_payload(text)
    if not prepared.get("ok"):
        prepared["auto_applied"] = False
        prepared["review_skipped"] = True
        return prepared

    payload = prepared.get("payload")
    if not isinstance(payload, dict):
        return {
            "status": "error",
            "reason": "auto-apply payload missing",
            "prepared": prepared,
            "auto_applied": False,
            "review_skipped": True,
        }

    if run_repo_edit is not None:
        try:
            result = run_repo_edit(payload, repo_root=repo_root)
        except TypeError:
            try:
                result = run_repo_edit(payload)
            except Exception as exc:
                return {
                    "status": "error",
                    "reason": f"run_repo_edit failed: {exc}",
                    "intent": prepared.get("intent", {}),
                    "payload": payload,
                    "auto_applied": False,
                    "review_skipped": True,
                }
        except Exception as exc:
            return {
                "status": "error",
                "reason": f"run_repo_edit failed: {exc}",
                "intent": prepared.get("intent", {}),
                "payload": payload,
                "auto_applied": False,
                "review_skipped": True,
            }

        result_payload = _to_dict(result)
        result_payload.setdefault("status", result_payload.get("status") or "applied")
        result_payload["auto_applied"] = True
        result_payload["review_skipped"] = True
        result_payload["intent"] = prepared.get("intent", {})
        result_payload["payload"] = payload
        result_payload["reason"] = result_payload.get("reason") or "auto-applied safe controlled_replace"
        return result_payload

    if run_code_edit_task is None:
        return {
            "status": "error",
            "reason": "run_repo_edit and run_code_edit_task are both unavailable",
            "intent": prepared.get("intent", {}),
            "payload": payload,
            "auto_applied": False,
            "review_skipped": True,
        }

    try:
        result = run_code_edit_task(text)
    except Exception as exc:
        return {
            "status": "error",
            "reason": f"run_code_edit_task failed: {exc}",
            "intent": prepared.get("intent", {}),
            "payload": payload,
            "auto_applied": False,
            "review_skipped": True,
        }

    result_payload = _to_dict(result)
    result_payload["auto_applied"] = True
    result_payload["review_skipped"] = True
    result_payload["intent"] = prepared.get("intent", {})
    result_payload["payload"] = payload
    return result_payload


def decide_review(
    review_id: str,
    decision: str,
    *,
    repo_root: str | Path = ".",
    reason: str = "",
) -> dict[str, Any]:
    """Compatibility function for old/manual review records."""

    normalized = str(decision or "").strip().lower()

    if normalized in {"apply", "approve", "accepted", "yes"}:
        if apply_review is None:
            return {
                "status": "error",
                "review_id": review_id,
                "reason": "apply_review unavailable",
            }
        return apply_review(review_id, repo_root=repo_root)

    if normalized in {"reject", "decline", "discard", "no"}:
        if reject_review is None:
            return {
                "status": "error",
                "review_id": review_id,
                "reason": "reject_review unavailable",
            }
        return reject_review(review_id, repo_root=repo_root, reason=reason or "rejected by user")

    return {
        "status": "blocked",
        "review_id": review_id,
        "reason": f"unknown review decision: {decision}",
    }


__all__ = ["run_code_edit_review_task", "decide_review"]
