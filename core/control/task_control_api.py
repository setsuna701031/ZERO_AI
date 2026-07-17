from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.control.task_control_models import TaskSubmission
from core.control.task_lifecycle_monitor import TaskLifecycleMonitor


def _text(value: Any) -> str:
    return str(value or "").strip()


def _task_id(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    for source in (value, value.get("task")):
        if not isinstance(source, dict):
            continue
        for key in ("task_id", "task_name", "id"):
            result = _text(source.get(key))
            if result:
                return result
    return ""


def _timestamp(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    text = _text(value)
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _last_result_summary(task: Dict[str, Any]) -> str:
    sources: List[Any] = [
        task,
        task.get("last_result"),
        task.get("last_step_result"),
        task.get("result"),
    ]
    results = task.get("results")
    if isinstance(results, list) and results:
        sources.append(results[-1])

    for source in sources:
        if isinstance(source, str) and source.strip():
            return source.strip()
        if not isinstance(source, dict):
            continue
        for key in ("final_answer", "result_summary", "summary", "message", "failure_message", "last_error", "error"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _issue_report(task: Dict[str, Any]) -> Any:
    sources = [task, task.get("result"), task.get("last_result"), task.get("last_step_result")]
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ("issue_report", "issue_reports", "issue_summary", "non_mainline_issues_found"):
            value = source.get(key)
            if value not in (None, "", [], {}):
                return copy.deepcopy(value)
    return None


def _task_view(task: Dict[str, Any]) -> Dict[str, Any]:
    status = _text(task.get("status")) or "unknown"
    current_stage = (
        _text(task.get("current_stage"))
        or _text(task.get("stage"))
        or _text(task.get("current_step"))
        or _text(task.get("current_step_index"))
        or status
    )
    return {
        "task_id": _task_id(task),
        "title": _text(task.get("title")),
        "instruction": _text(task.get("goal") or task.get("instruction")),
        "task_type": _text(task.get("task_type")),
        "status": status,
        "current_stage": current_stage,
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
        "last_result_summary": _last_result_summary(task),
        "issue_report": _issue_report(task),
    }


class TaskControlAPI:
    """Local task-control boundary over public scheduler and repository APIs."""

    def __init__(self, submission_gateway: Any, task_repository: Any = None) -> None:
        self.submission_gateway = submission_gateway
        self.task_repository = task_repository or getattr(submission_gateway, "task_repo", None)
        self.lifecycle_monitor = TaskLifecycleMonitor(self.task_repository)

    @classmethod
    def with_workspace(cls, workspace_dir: str | Path = "workspace") -> "TaskControlAPI":
        from core.tasks.scheduler import Scheduler
        from core.tasks.task_repository import TaskRepository

        workspace = Path(workspace_dir)
        repository = TaskRepository(db_path=str(workspace / "tasks.json"))
        scheduler = Scheduler(task_repo=repository, workspace_dir=str(workspace))
        return cls(submission_gateway=scheduler, task_repository=repository)

    def submit_task(
        self,
        *,
        title: str,
        instruction: str,
        task_type: str = "engineering_task",
        mode: str = "",
    ) -> Dict[str, Any]:
        request = TaskSubmission(title=title, instruction=instruction, task_type=task_type, mode=mode)
        error = request.validate()
        if error:
            return {"ok": False, "accepted": False, "task_id": "", "reason": error}

        submit = getattr(self.submission_gateway, "submit_task", None)
        if not callable(submit):
            return {
                "ok": False,
                "accepted": False,
                "task_id": "",
                "reason": "Task submission boundary not available",
            }

        try:
            raw = submit(**request.scheduler_kwargs())
        except Exception as exc:
            return {
                "ok": False,
                "accepted": False,
                "task_id": "",
                "reason": f"Task submission failed: {exc}",
            }

        result = raw if isinstance(raw, dict) else {"ok": bool(raw)}
        accepted = bool(result.get("ok"))
        return {
            "ok": accepted,
            "accepted": accepted,
            "task_id": _task_id(result),
            "reason": "" if accepted else _text(result.get("error") or result.get("reason") or "Task rejected"),
            "status": _text(result.get("status")),
        }

    def inspect_task(self, task_id: str) -> Dict[str, Any]:
        normalized_id = _text(task_id)
        if not normalized_id:
            return {"ok": False, "task_id": "", "reason": "task_id is required"}

        lifecycle = self.lifecycle_monitor.inspect(normalized_id)
        if not lifecycle.get("ok"):
            return lifecycle
        return {
            **lifecycle,
            "last_result_summary": lifecycle.get("result_summary") or lifecycle.get("error_summary", ""),
            "issue_report": lifecycle.get("issue_reports", []),
        }

    def monitor_task(self, task_id: str) -> Dict[str, Any]:
        return self.lifecycle_monitor.inspect(task_id)

    def list_recent_tasks(self, limit: int = 20) -> Dict[str, Any]:
        list_tasks = getattr(self.task_repository, "list_tasks", None)
        if not callable(list_tasks):
            return {"ok": False, "tasks": [], "reason": "Task repository read boundary not available"}

        tasks = list_tasks()
        records = [task for task in tasks if isinstance(task, dict)] if isinstance(tasks, list) else []
        records.sort(
            key=lambda task: (
                _timestamp(task.get("updated_at") or task.get("created_at")),
                _task_id(task),
            ),
            reverse=True,
        )
        bounded_limit = max(1, min(int(limit or 20), 100))
        return {"ok": True, "tasks": [_task_view(task) for task in records[:bounded_limit]]}

    def request_cancel(self, task_id: str) -> Dict[str, Any]:
        normalized_id = _text(task_id)
        cancel = getattr(self.submission_gateway, "cancel_task", None)
        if not callable(cancel):
            return {
                "ok": False,
                "task_id": normalized_id,
                "cancel_supported": False,
                "reason": "Runtime cancellation boundary not implemented yet",
            }
        if not normalized_id:
            return {
                "ok": False,
                "task_id": "",
                "cancel_supported": True,
                "reason": "task_id is required",
            }

        try:
            raw = cancel(normalized_id)
        except Exception as exc:
            return {
                "ok": False,
                "task_id": normalized_id,
                "cancel_supported": True,
                "reason": f"Cancellation request failed: {exc}",
            }
        result = raw if isinstance(raw, dict) else {"ok": bool(raw)}
        return {
            "ok": bool(result.get("ok")),
            "task_id": normalized_id,
            "cancel_supported": True,
            "status": _text(result.get("status")),
            "reason": "" if result.get("ok") else _text(result.get("error") or result.get("reason") or "Cancellation rejected"),
        }


__all__ = ["TaskControlAPI"]
