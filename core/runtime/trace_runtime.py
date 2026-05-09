from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Dict, Optional

from core.tools.execution_trace import ExecutionTrace


class TraceRuntime:
    """
    Trace runtime boundary container.

    This module preserves Scheduler legacy trace behavior while moving trace
    path/load/save/event operations behind a runtime boundary.
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

    def load_scheduler_trace_for_task(
        self,
        *,
        task: Dict[str, Any],
        tasks_root: str | Path,
        task_id: str = "",
    ) -> ExecutionTrace:
        trace_path = self.scheduler_trace_file_for_task(
            task=task,
            tasks_root=tasks_root,
            task_id=task_id,
        )
        trace = ExecutionTrace(trace_file=trace_path)
        trace.load(trace_path)
        task["trace_file"] = trace_path
        return trace

    def save_scheduler_trace_for_task(
        self,
        *,
        task: Dict[str, Any],
        trace: ExecutionTrace,
        tasks_root: str | Path,
        task_id: str = "",
    ) -> Optional[str]:
        trace_path = self.scheduler_trace_file_for_task(
            task=task,
            tasks_root=tasks_root,
            task_id=task_id,
        )
        saved = trace.save(trace_path)
        task["trace_file"] = trace_path
        return saved

    def scheduler_trace_summary(
        self,
        *,
        scheduler: Any,
        trace: ExecutionTrace,
        task: Dict[str, Any],
        summary: str,
        tick: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        trace.add_summary_event(
            task_id=scheduler._extract_task_id(task),
            summary=summary,
            tick=tick,
            extra=copy.deepcopy(extra) if isinstance(extra, dict) else None,
        )

    def scheduler_trace_status(
        self,
        *,
        scheduler: Any,
        trace: ExecutionTrace,
        task: Dict[str, Any],
        status: str,
        tick: Optional[int] = None,
        final_answer: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        trace.add_status_event(
            task_id=scheduler._extract_task_id(task),
            status=status,
            tick=tick,
            final_answer=final_answer,
            extra=copy.deepcopy(extra) if isinstance(extra, dict) else None,
        )

    def scheduler_trace_step(
        self,
        *,
        scheduler: Any,
        trace: ExecutionTrace,
        task: Dict[str, Any],
        step_index: int,
        step: Dict[str, Any],
        ok: bool,
        result: Optional[Dict[str, Any]] = None,
        error: str = "",
        tick: Optional[int] = None,
    ) -> None:
        trace.add_step_event(
            task_id=scheduler._extract_task_id(task),
            step_index=step_index,
            step=copy.deepcopy(step),
            ok=bool(ok),
            result=copy.deepcopy(result) if isinstance(result, dict) else None,
            error=str(error or ""),
            tick=tick,
        )

    def scheduler_trace_replan(
        self,
        *,
        scheduler: Any,
        trace: ExecutionTrace,
        task: Dict[str, Any],
        tick: Optional[int],
        replan_result: Dict[str, Any],
    ) -> None:
        raw_replan_result = replan_result.get("raw_replan_result", {})
        if not isinstance(raw_replan_result, dict):
            raw_replan_result = {}

        plan = raw_replan_result.get("plan", {})
        if not isinstance(plan, dict):
            plan = {}

        meta = plan.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}

        new_steps = plan.get("steps", [])
        if not isinstance(new_steps, list):
            new_steps = []

        trace.add_replan_event(
            task_id=scheduler._extract_task_id(task),
            failed_step_index=int(meta.get("failed_step_index", -1) or -1),
            failed_step_type=str(meta.get("failed_step_type") or ""),
            error_type=str(meta.get("error_type") or ""),
            failed_error=str(meta.get("failed_error") or ""),
            repair_mode=str(meta.get("repair_mode") or ""),
            replan_count=int(replan_result.get("replan_count", task.get("replan_count", 0)) or 0),
            max_replans=int(meta.get("max_replans", task.get("max_replans", 0)) or 0),
            new_steps=copy.deepcopy(new_steps),
            tick=tick,
        )

    def trace_summary(self, trace: Any) -> Dict[str, Any]:
        if isinstance(trace, dict):
            events = trace.get("events")
            if isinstance(events, list):
                return {"event_count": len(events), "has_events": bool(events)}

        if isinstance(trace, list):
            return {"event_count": len(trace), "has_events": bool(trace)}

        return {"event_count": 0, "has_events": False}

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