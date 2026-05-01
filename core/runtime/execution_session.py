from __future__ import annotations

from dataclasses import dataclass, field, asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4


@dataclass
class ExecutionSession:
    session_id: str
    task_id: str | None
    task_summary: str
    started_at: str
    ended_at: str | None
    status: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    audit_request_ids: List[str] = field(default_factory=list)

    @classmethod
    def start(cls, task: Any) -> "ExecutionSession":
        return cls(
            session_id=str(uuid4()),
            task_id=_task_id(task),
            task_summary=_task_summary(task),
            started_at=_now_iso(),
            ended_at=None,
            status="running",
        )

    def add_step(self, step_name: str, status: str, detail: Any = None) -> None:
        self.steps.append(
            {
                "step_name": str(step_name or ""),
                "status": str(status or ""),
                "detail": _summarize(detail),
                "timestamp": _now_iso(),
            }
        )

    def add_tool_result(self, tool_result: Any) -> None:
        payload = _as_dict(tool_result)
        request_id = _find_first(payload, "request_id")
        if request_id:
            request_id_text = str(request_id)
            if request_id_text not in self.audit_request_ids:
                self.audit_request_ids.append(request_id_text)

        output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        source_payload = output or result or payload

        self.tool_results.append(
            {
                "request_id": str(request_id) if request_id else None,
                "tool": str(payload.get("tool") or source_payload.get("tool") or payload.get("tool_name") or ""),
                "ok": bool(payload.get("ok", source_payload.get("ok", False))),
                "side_effect_level": str(
                    payload.get("side_effect_level")
                    or source_payload.get("side_effect_level")
                    or "none"
                ),
                "summary": _summarize(source_payload),
            }
        )

    def finish(self, status: str = "finished") -> None:
        self.status = str(status or "finished")
        self.ended_at = _now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "task_summary": self.task_summary,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "status": self.status,
            "steps": list(self.steps),
            "tool_results": list(self.tool_results),
            "audit_request_ids": list(self.audit_request_ids),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_id(task: Any) -> str | None:
    if not isinstance(task, dict):
        return None
    value = task.get("id") or task.get("task_id") or task.get("task_name")
    text = str(value or "").strip()
    return text or None


def _task_summary(task: Any) -> str:
    if isinstance(task, dict):
        for key in ("title", "goal", "input", "user_input", "description"):
            value = task.get(key)
            if value:
                return _summarize_string(str(value))
    return _summarize_string(str(task or ""))


def _as_dict(value: Any) -> Dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    return {"result": value}


def _find_first(value: Any, key: str, depth: int = 0) -> Any:
    if depth > 5:
        return None
    if isinstance(value, dict):
        found = value.get(key)
        if found:
            return found
        for nested in value.values():
            found = _find_first(nested, key, depth + 1)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_first(item, key, depth + 1)
            if found:
                return found
    return None


def _summarize(value: Any, depth: int = 0) -> Any:
    if depth >= 4:
        return _type_summary(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _summarize_string(value)
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _summarize(asdict(value), depth + 1)
    if isinstance(value, dict):
        summary: Dict[str, Any] = {}
        items = list(value.items())
        for key, item in items[:12]:
            key_text = str(key)
            if key_text.lower() in {"content", "file_content", "raw_content", "body", "stdout", "stderr"}:
                summary[key_text] = _type_summary(item)
            else:
                summary[key_text] = _summarize(item, depth + 1)
        if len(items) > 12:
            summary["truncated_keys"] = len(items) - 12
        return summary
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        summary_list = [_summarize(item, depth + 1) for item in items[:8]]
        if len(items) > 8:
            summary_list.append({"truncated_items": len(items) - 8})
        return summary_list
    return _summarize_string(str(value))


def _summarize_string(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(normalized) <= 200:
        return normalized
    return f"{normalized[:200]}... <truncated len={len(normalized)}>"


def _type_summary(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        return {"type": "str", "length": len(value)}
    if isinstance(value, dict):
        return {"type": "dict", "keys": len(value)}
    if isinstance(value, (list, tuple, set)):
        return {"type": type(value).__name__, "items": len(value)}
    return {"type": type(value).__name__}
