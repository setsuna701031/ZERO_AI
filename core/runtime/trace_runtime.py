from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional


class TraceRuntime:
    """
    Trace runtime boundary container.

    This module is intentionally conservative:
    - It can build new standalone trace paths.
    - It can also preserve Scheduler legacy trace path behavior.
    - It does not replace trace persistence schema.
    """

    def __init__(self, repo_root: str | Path | None = None) -> None:
        self.repo_root = Path(repo_root or Path.cwd()).resolve()

    def trace_file_for_task(self, task: Dict[str, Any]) -> Path:
        task_id = self._task_id(task)
        return self.repo_root / "workspace" / "runtime_traces" / f"{task_id}.json"

    def scheduler_trace_file_for_task(
        self,
        *,
        task: Dict[str, Any],
        tasks_root: str | Path,
        task_id: str = "",
    ) -> str:
        if not isinstance(task, dict):
            return os.path.join(str(tasks_root), "unknown_task", "trace.json")

        task_dir = str(task.get("task_dir") or "").strip()

        if not task_dir:
            resolved_task_id = str(task_id or self._task_id(task) or "unknown_task").strip()
            task_dir = os.path.join(str(tasks_root), resolved_task_id)

        os.makedirs(task_dir, exist_ok=True)

        trace_file = str(task.get("trace_file") or "").strip()

        if trace_file:
            return trace_file

        return os.path.join(task_dir, "trace.json")

    def trace_summary(self, trace: Any) -> Dict[str, Any]:
        if isinstance(trace, dict):
            events = trace.get("events")
            if isinstance(events, list):
                return {
                    "event_count": len(events),
                    "has_events": bool(events),
                }

        if isinstance(trace, list):
            return {
                "event_count": len(trace),
                "has_events": bool(trace),
            }

        return {
            "event_count": 0,
            "has_events": False,
        }

    def trace_status(self, trace: Any) -> str:
        if isinstance(trace, dict):
            status = str(trace.get("status") or "").strip()
            if status:
                return status

            events = trace.get("events")
            if isinstance(events, list) and events:
                last = events[-1]
                if isinstance(last, dict):
                    event_status = str(last.get("status") or "").strip()
                    if event_status:
                        return event_status

        return "unknown"

    def trace_step(
        self,
        *,
        step_id: str = "",
        status: str = "",
        message: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "type": "step",
            "step_id": str(step_id or ""),
            "status": str(status or ""),
            "message": str(message or ""),
            "payload": dict(payload or {}),
        }

    def trace_replan(
        self,
        *,
        reason: str = "",
        status: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "type": "replan",
            "reason": str(reason or ""),
            "status": str(status or ""),
            "payload": dict(payload or {}),
        }

    def _task_id(self, task: Dict[str, Any]) -> str:
        if not isinstance(task, dict):
            return "unknown_task"

        for key in ("task_id", "id", "name", "task_name"):
            value = str(task.get(key) or "").strip()
            if value:
                return self._safe_name(value)

        return "unknown_task"

    def _safe_name(self, value: str) -> str:
        safe = []

        for char in value:
            if char.isalnum() or char in {"-", "_", "."}:
                safe.append(char)
            else:
                safe.append("_")

        text = "".join(safe).strip("._")

        return text or "unknown_task"


def build_trace_runtime(repo_root: str | Path | None = None) -> TraceRuntime:
    return TraceRuntime(repo_root=repo_root)