from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional


_RUNTIME_TERMINAL_OK = {"finished", "success", "completed", "done", "ok"}
_RUNTIME_TERMINAL_FAIL = {"failed", "error", "cancelled", "canceled"}


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, Mapping):
        return dict(value.items())
    return {}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _pick_first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) not in (None, ""):
            return mapping.get(key)
    return None


def normalize_runtime_native_status(value: Any) -> str:
    text = _clean_text(value).lower()
    if text in _RUNTIME_TERMINAL_OK:
        return "finished"
    if text in _RUNTIME_TERMINAL_FAIL:
        return "failed"
    if text in {"queued", "pending", "created", "new"}:
        return "queued"
    if text in {"running", "in_progress", "executing"}:
        return "running"
    if text in {"blocked", "waiting"}:
        return "blocked"
    if text in {"retry", "retrying"}:
        return "retrying"
    return text or "queued"


@dataclass(frozen=True)
class RuntimeNativeEntryRequest:
    goal: str = ""
    task: Dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    runtime_session_id: str = ""
    source: str = "runtime_native_entry_adapter"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "goal": self.goal,
            "task": dict(self.task),
            "session_id": self.session_id,
            "runtime_session_id": self.runtime_session_id,
            "source": self.source,
            "metadata": dict(self.metadata),
        }
        if self.session_id and "session_id" not in payload["task"]:
            payload["task"]["session_id"] = self.session_id
        if self.runtime_session_id and "runtime_session_id" not in payload["task"]:
            payload["task"]["runtime_session_id"] = self.runtime_session_id
        if self.goal and "goal" not in payload["task"]:
            payload["task"]["goal"] = self.goal
        return payload


def normalize_runtime_native_entry_request(value: Any) -> Dict[str, Any]:
    raw = _as_dict(value)
    task = _as_dict(_pick_first(raw, "task", "payload", "request"))
    if not task:
        task = dict(raw)

    metadata = _as_dict(_pick_first(raw, "metadata", "meta"))
    task_metadata = _as_dict(task.get("metadata"))
    if task_metadata:
        merged = dict(task_metadata)
        merged.update(metadata)
        metadata = merged

    goal = _clean_text(_pick_first(raw, "goal", "goal_text", "instruction", "prompt"))
    if not goal:
        goal = _clean_text(_pick_first(task, "goal", "goal_text", "instruction", "prompt", "title"))

    session_id = _clean_text(_pick_first(raw, "session_id", "operator_session_id"))
    if not session_id:
        session_id = _clean_text(_pick_first(task, "session_id", "operator_session_id"))

    runtime_session_id = _clean_text(_pick_first(raw, "runtime_session_id", "runtime_id"))
    if not runtime_session_id:
        runtime_session_id = _clean_text(_pick_first(task, "runtime_session_id", "runtime_id"))
    if not runtime_session_id:
        runtime_session_id = session_id

    source = _clean_text(_pick_first(raw, "source", "entry_source")) or "runtime_native_entry_adapter"

    return RuntimeNativeEntryRequest(
        goal=goal,
        task=task,
        session_id=session_id,
        runtime_session_id=runtime_session_id,
        source=source,
        metadata=metadata,
    ).to_dict()


def build_runtime_native_entry_request(
    goal: Any = "",
    task: Optional[Mapping[str, Any]] = None,
    session_id: Any = "",
    runtime_session_id: Any = "",
    metadata: Optional[Mapping[str, Any]] = None,
    source: str = "runtime_native_entry_adapter",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "goal": _clean_text(goal),
        "task": dict(task or {}),
        "session_id": _clean_text(session_id),
        "runtime_session_id": _clean_text(runtime_session_id),
        "metadata": dict(metadata or {}),
        "source": source,
    }
    return normalize_runtime_native_entry_request(payload)


def _call_first_available(target: Any, request: Dict[str, Any]) -> Any:
    for name in ("run_native", "run_entry", "run_request", "run", "execute", "submit", "admit", "dispatch"):
        fn = getattr(target, name, None)
        if callable(fn):
            return fn(request)
    raise AttributeError("Runtime native mainline object has no supported entry method")


def _native_entry_status_for_result(result: Dict[str, Any]) -> str:
    if "status" in result:
        return normalize_runtime_native_status(result.get("status"))
    if result.get("ok") is True:
        return "finished"
    if result.get("ok") is False:
        return "failed"
    return "queued"


def normalize_runtime_native_entry_result(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        result = dict(value)
    else:
        result = {"ok": True, "result": value}

    return {
        **result,
        "status": _native_entry_status_for_result(result),
    }


class RuntimeNativeEntryAdapter:
    def __init__(self, mainline: Any = None) -> None:
        self.mainline = mainline

    def normalize(self, value: Any) -> Dict[str, Any]:
        return normalize_runtime_native_entry_request(value)

    def run(self, value: Any, mainline: Any = None) -> Dict[str, Any]:
        request = normalize_runtime_native_entry_request(value)
        target = mainline if mainline is not None else self.mainline
        if target is None:
            return {
                "ok": True,
                "status": "queued",
                "request": request,
                "adapter": "runtime_native_entry_adapter",
            }
        return normalize_runtime_native_entry_result(_call_first_available(target, request))

    execute = run
    admit = run
    dispatch = run

    def __call__(self, value: Any, mainline: Any = None) -> Dict[str, Any]:
        return self.run(value, mainline=mainline)


def run_runtime_native_entry(mainline: Any, value: Any) -> Dict[str, Any]:
    return RuntimeNativeEntryAdapter(mainline).run(value)


def run_via_runtime_native_mainline(**kwargs: Any) -> Any:
    runner = kwargs.get("runner")
    if callable(runner):
        return runner()

    mainline = kwargs.get("mainline")
    payload = kwargs.get("payload")
    if payload is None:
        payload = kwargs.get("request")
    if payload is None:
        payload = kwargs.get("task")
    if payload is None:
        payload = kwargs

    if mainline is not None:
        return run_runtime_native_entry(mainline, payload)

    return RuntimeNativeEntryAdapter().run(payload)


__all__ = [
    "RuntimeNativeEntryAdapter",
    "RuntimeNativeEntryRequest",
    "build_runtime_native_entry_request",
    "normalize_runtime_native_entry_request",
    "normalize_runtime_native_entry_result",
    "normalize_runtime_native_status",
    "run_runtime_native_entry",
    "run_via_runtime_native_mainline",
]
