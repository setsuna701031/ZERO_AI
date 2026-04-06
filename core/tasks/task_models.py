# core/tasks/task_models.py

from typing import Any, Dict, List, Optional, Set
from datetime import datetime


def now_iso() -> str:
    return datetime.utcnow().isoformat()


class StepRecord:
    """
    任務中的一步
    """

    def __init__(
        self,
        step_id: str,
        title: str,
        description: str = "",
        status: str = "pending",
        tool: Optional[str] = None,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Any = None,
        error: Optional[str] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> None:
        self.step_id = step_id
        self.title = title
        self.description = description
        self.status = status
        self.tool = tool
        self.input_data = input_data or {}
        self.output_data = output_data
        self.error = error
        self.started_at = started_at
        self.finished_at = finished_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "tool": self.tool,
            "input": self.input_data,
            "output": self.output_data,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepRecord":
        return cls(
            step_id=data.get("step_id", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            status=data.get("status", "pending"),
            tool=data.get("tool"),
            input_data=data.get("input", {}),
            output_data=data.get("output"),
            error=data.get("error"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
        )


class TaskRecord:
    """
    任務資料模型
    """

    FINAL_STATUSES = {"done", "failed", "cancelled"}
    READY_SOURCE_STATUSES = {"pending", "queued", "waiting", "blocked"}
    SUCCESS_DEPENDENCY_STATUSES = {"done"}

    def __init__(
        self,
        task_id: str,
        title: str,
        goal: str,
        status: str = "pending",
        workspace: Optional[str] = None,
        steps: Optional[List[StepRecord]] = None,
        current_step_index: int = -1,
        result: Any = None,
        error: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        depends_on: Optional[List[str]] = None,
        priority: int = 100,
        retry_count: int = 0,
        max_retries: int = 0,
        timeout_seconds: Optional[int] = None,
        blocked_reason: Optional[str] = None,
    ) -> None:
        self.task_id = task_id
        self.title = title
        self.goal = goal
        self.status = status
        self.workspace = workspace
        self.steps = steps or []
        self.current_step_index = current_step_index
        self.result = result
        self.error = error
        self.history = history or []
        self.created_at = created_at or now_iso()
        self.updated_at = updated_at or now_iso()
        self.metadata = metadata or {}

        self.depends_on = self._normalize_depends_on(depends_on, self.task_id)
        self.priority = self._normalize_priority(priority)
        self.retry_count = self._normalize_non_negative_int(retry_count, "retry_count")
        self.max_retries = self._normalize_non_negative_int(max_retries, "max_retries")
        self.timeout_seconds = self._normalize_optional_positive_int(timeout_seconds, "timeout_seconds")
        self.blocked_reason = blocked_reason

    @staticmethod
    def _normalize_non_negative_int(value: Any, field_name: str) -> int:
        if value is None:
            return 0
        if isinstance(value, bool):
            raise ValueError(f"{field_name} must be an integer")
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{field_name} must be an integer")
        if parsed < 0:
            raise ValueError(f"{field_name} must be >= 0")
        return parsed

    @staticmethod
    def _normalize_optional_positive_int(value: Any, field_name: str) -> Optional[int]:
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            raise ValueError(f"{field_name} must be an integer")
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{field_name} must be an integer")
        if parsed <= 0:
            raise ValueError(f"{field_name} must be > 0")
        return parsed

    @staticmethod
    def _normalize_priority(value: Any) -> int:
        if value is None:
            return 100
        if isinstance(value, bool):
            raise ValueError("priority must be an integer")
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError("priority must be an integer")

    @staticmethod
    def _normalize_depends_on(depends_on: Optional[List[str]], task_id: Optional[str] = None) -> List[str]:
        if depends_on is None:
            return []

        if not isinstance(depends_on, list):
            raise ValueError("depends_on must be a list of task_id strings")

        normalized: List[str] = []
        seen: Set[str] = set()

        for item in depends_on:
            if not isinstance(item, str):
                raise ValueError("depends_on must contain only strings")

            dep_id = item.strip()
            if not dep_id:
                continue

            if task_id and dep_id == task_id:
                raise ValueError("task cannot depend on itself")

            if dep_id in seen:
                continue

            seen.add(dep_id)
            normalized.append(dep_id)

        return normalized

    def mark_updated(self) -> None:
        self.updated_at = now_iso()

    def add_history(self, from_status: Optional[str], to_status: str, reason: str) -> None:
        self.history.append(
            {
                "from": from_status,
                "to": to_status,
                "reason": reason,
                "timestamp": now_iso(),
            }
        )
        self.updated_at = now_iso()

    def set_status(self, new_status: str, reason: str = "") -> None:
        old_status = self.status
        self.status = new_status
        self.add_history(old_status, new_status, reason or "status updated")

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def increment_retry(self) -> None:
        self.retry_count += 1
        self.mark_updated()

    def reset_retry(self) -> None:
        self.retry_count = 0
        self.mark_updated()

    def set_blocked(self, reason: str) -> None:
        old_status = self.status
        self.status = "blocked"
        self.blocked_reason = reason
        self.add_history(old_status, "blocked", reason)

    def clear_blocked(self) -> None:
        self.blocked_reason = None
        self.mark_updated()

    def dependency_status_map(self, task_map: Dict[str, "TaskRecord"]) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for dep_id in self.depends_on:
            dep_task = task_map.get(dep_id)
            result[dep_id] = dep_task.status if dep_task else "missing"
        return result

    def missing_dependencies(self, task_map: Dict[str, "TaskRecord"]) -> List[str]:
        return [dep_id for dep_id in self.depends_on if dep_id not in task_map]

    def unmet_dependencies(self, task_map: Dict[str, "TaskRecord"]) -> List[str]:
        unmet: List[str] = []
        for dep_id in self.depends_on:
            dep_task = task_map.get(dep_id)
            if dep_task is None:
                unmet.append(dep_id)
                continue
            if dep_task.status not in self.SUCCESS_DEPENDENCY_STATUSES:
                unmet.append(dep_id)
        return unmet

    def dependencies_done(self, task_map: Dict[str, "TaskRecord"]) -> bool:
        return len(self.unmet_dependencies(task_map)) == 0

    def is_ready(self, task_map: Dict[str, "TaskRecord"]) -> bool:
        if self.status not in self.READY_SOURCE_STATUSES:
            return False
        return self.dependencies_done(task_map)

    def is_blocked(self, task_map: Dict[str, "TaskRecord"]) -> bool:
        if self.status in self.FINAL_STATUSES:
            return False
        return not self.dependencies_done(task_map)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "goal": self.goal,
            "status": self.status,
            "workspace": self.workspace,
            "current_step_index": self.current_step_index,
            "result": self.result,
            "error": self.error,
            "history": self.history,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
            "steps": [step.to_dict() for step in self.steps],
            "depends_on": list(self.depends_on),
            "priority": self.priority,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "blocked_reason": self.blocked_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRecord":
        steps_data = data.get("steps", [])
        steps = [StepRecord.from_dict(s) for s in steps_data]

        return cls(
            task_id=data.get("task_id", ""),
            title=data.get("title", ""),
            goal=data.get("goal", ""),
            status=data.get("status", "pending"),
            workspace=data.get("workspace"),
            steps=steps,
            current_step_index=data.get("current_step_index", -1),
            result=data.get("result"),
            error=data.get("error"),
            history=data.get("history", []),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            metadata=data.get("metadata", {}),
            depends_on=data.get("depends_on", []),
            priority=data.get("priority", 100),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 0),
            timeout_seconds=data.get("timeout_seconds"),
            blocked_reason=data.get("blocked_reason"),
        )