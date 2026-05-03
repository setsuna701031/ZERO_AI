from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


MAX_AUDIT_TEXT_CHARS = 12000
MAX_AUDIT_DEPTH = 8
DROP_AUDIT_KEYS = {"runtime_state", "task", "raw_task", "raw_result", "runner_result"}


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_value(value: Any, depth: int = 0) -> Any:
    if depth > MAX_AUDIT_DEPTH:
        return "<truncated: max depth reached>"

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        if len(value) <= MAX_AUDIT_TEXT_CHARS:
            return value
        return value[:MAX_AUDIT_TEXT_CHARS] + f"\n<truncated: {len(value) - MAX_AUDIT_TEXT_CHARS} characters omitted>"

    if isinstance(value, tuple):
        value = list(value)

    if isinstance(value, list):
        return [_safe_json_value(item, depth + 1) for item in value[-50:]]

    if isinstance(value, dict):
        safe: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in DROP_AUDIT_KEYS:
                safe[key_text] = "<omitted: recursive/heavy payload>"
                continue
            safe[key_text] = _safe_json_value(item, depth + 1)
        return safe

    return str(value)


class AuditLogger:
    """Append-only per-task audit log.

    Audit is observability only. It must never break task execution.
    Runtime state remains the machine source of truth; audit_log.jsonl is the
    human/debug/replay stream.
    """

    def __init__(self, workspace_root: str = "workspace") -> None:
        self.workspace_root = str(workspace_root or "workspace")

    def task_dir(self, task: Dict[str, Any]) -> str:
        task_dir = str(task.get("task_dir") or "").strip()
        if task_dir:
            return task_dir

        runtime_state_file = str(task.get("runtime_state_file") or "").strip()
        if runtime_state_file:
            try:
                return str(Path(runtime_state_file).parent)
            except Exception:
                pass

        task_id = str(
            task.get("task_id")
            or task.get("task_name")
            or task.get("id")
            or "unknown_task"
        ).strip() or "unknown_task"
        return os.path.join(self.workspace_root, "tasks", task_id)

    def audit_file_for_task(self, task: Dict[str, Any]) -> str:
        return os.path.join(self.task_dir(task), "audit_log.jsonl")

    def audit_file_for_payload(self, payload: Dict[str, Any]) -> str:
        runtime_state_file = str(payload.get("runtime_state_file") or "").strip()
        if runtime_state_file:
            try:
                return str(Path(runtime_state_file).parent / "audit_log.jsonl")
            except Exception:
                pass

        task_dir = str(payload.get("task_dir") or "").strip()
        if task_dir:
            return os.path.join(task_dir, "audit_log.jsonl")

        workspace_root = str(payload.get("workspace_root") or self.workspace_root or "workspace")
        task_id = str(
            payload.get("task_id")
            or payload.get("task_name")
            or payload.get("id")
            or "unknown_task"
        ).strip() or "unknown_task"
        return os.path.join(workspace_root, "tasks", task_id, "audit_log.jsonl")

    def log_event(
        self,
        task: Dict[str, Any],
        event: str,
        data: Optional[Dict[str, Any]] = None,
        *,
        source: str = "runtime",
    ) -> None:
        try:
            if not isinstance(task, dict):
                task = {}
            task_id = str(task.get("task_id") or task.get("task_name") or task.get("id") or "").strip()
            record = {
                "ts": _utc_now_text(),
                "event": str(event or "event"),
                "source": str(source or "runtime"),
                "task_id": task_id,
                "task_name": str(task.get("task_name") or task_id or ""),
                "status": str(task.get("status") or ""),
                "data": _safe_json_value(data if isinstance(data, dict) else {}),
            }
            path = self.audit_file_for_task(task)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        except Exception:
            pass

    def log_payload_event(
        self,
        payload: Dict[str, Any],
        event: str,
        data: Optional[Dict[str, Any]] = None,
        *,
        source: str = "review",
    ) -> None:
        try:
            if not isinstance(payload, dict):
                payload = {}
            task_id = str(payload.get("task_id") or payload.get("task_name") or payload.get("id") or "").strip()
            record = {
                "ts": _utc_now_text(),
                "event": str(event or "event"),
                "source": str(source or "review"),
                "task_id": task_id,
                "task_name": str(payload.get("task_name") or task_id or ""),
                "review_id": str(payload.get("review_id") or ""),
                "file_path": str(payload.get("file_path") or ""),
                "data": _safe_json_value(data if isinstance(data, dict) else {}),
            }
            path = self.audit_file_for_payload(payload)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        except Exception:
            pass


def log_task_event(task: Dict[str, Any], event: str, data: Optional[Dict[str, Any]] = None, *, workspace_root: str = "workspace", source: str = "runtime") -> None:
    AuditLogger(workspace_root=workspace_root).log_event(task, event, data, source=source)


def log_payload_event(payload: Dict[str, Any], event: str, data: Optional[Dict[str, Any]] = None, *, workspace_root: str = "workspace", source: str = "review") -> None:
    AuditLogger(workspace_root=workspace_root).log_payload_event(payload, event, data, source=source)
