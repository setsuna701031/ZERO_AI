from __future__ import annotations

import json
import os
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@dataclass
class TaskStep:
    step_id: str
    title: str
    description: str = ""
    status: str = "pending"   # pending / running / done / failed / skipped
    result: Optional[str] = None
    error: Optional[str] = None
    tool: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "tool": self.tool,
            "tool_input": deepcopy(self.tool_input),
            "metadata": deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskStep":
        return cls(
            step_id=data.get("step_id", str(uuid.uuid4())),
            title=data.get("title", ""),
            description=data.get("description", ""),
            status=data.get("status", "pending"),
            result=data.get("result"),
            error=data.get("error"),
            tool=data.get("tool"),
            tool_input=deepcopy(data.get("tool_input")) if data.get("tool_input") is not None else None,
            metadata=deepcopy(data.get("metadata", {})),
            created_at=data.get("created_at", _utc_now()),
            updated_at=data.get("updated_at", _utc_now()),
        )


@dataclass
class TaskRecord:
    task_id: str
    goal: str
    status: str = "created"   # created / planned / queued / running / completed / failed / paused / cancelled
    current_step_index: int = 0
    steps: List[TaskStep] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    priority: int = 0
    source: str = "user"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status,
            "current_step_index": self.current_step_index,
            "steps": [step.to_dict() for step in self.steps],
            "history": deepcopy(self.history),
            "result": self.result,
            "error": self.error,
            "priority": self.priority,
            "source": self.source,
            "metadata": deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRecord":
        return cls(
            task_id=data.get("task_id", str(uuid.uuid4())),
            goal=data.get("goal", ""),
            status=data.get("status", "created"),
            current_step_index=data.get("current_step_index", 0),
            steps=[TaskStep.from_dict(item) for item in data.get("steps", [])],
            history=deepcopy(data.get("history", [])),
            result=data.get("result"),
            error=data.get("error"),
            priority=data.get("priority", 0),
            source=data.get("source", "user"),
            metadata=deepcopy(data.get("metadata", {})),
            created_at=data.get("created_at", _utc_now()),
            updated_at=data.get("updated_at", _utc_now()),
        )


class TaskRepository:
    """
    單一責任：
    - 保存 / 讀取 task records
    - 更新 task runtime state
    - 管理 steps / history / metadata

    不負責：
    - build_plan_for_goal
    - LLM 規劃
    - scheduler orchestration
    - 真正執行 step
    """

    def __init__(self, file_path: str = "data/tasks/task_memory.json") -> None:
        self.file_path = file_path
        self.tasks: Dict[str, TaskRecord] = {}
        self._ensure_storage()
        self.load()

    # ------------------------------------------------------------------
    # storage
    # ------------------------------------------------------------------
    def _ensure_storage(self) -> None:
        folder = os.path.dirname(self.file_path)
        if folder:
            os.makedirs(folder, exist_ok=True)

        if not os.path.exists(self.file_path):
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump({"tasks": []}, f, ensure_ascii=False, indent=2)

    def load(self) -> None:
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            raw = {"tasks": []}

        tasks = raw.get("tasks", [])
        self.tasks = {}
        for item in tasks:
            record = TaskRecord.from_dict(item)
            self.tasks[record.task_id] = record

    def save(self) -> None:
        payload = {
            "tasks": [task.to_dict() for task in self.tasks.values()]
        }
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # basic CRUD
    # ------------------------------------------------------------------
    def create_task(
        self,
        goal: str,
        priority: int = 0,
        source: str = "user",
        metadata: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> TaskRecord:
        record = TaskRecord(
            task_id=task_id or str(uuid.uuid4()),
            goal=goal,
            priority=priority,
            source=source,
            metadata=deepcopy(metadata or {}),
        )
        self.tasks[record.task_id] = record
        self.append_history(record.task_id, "task_created", {"goal": goal})
        self.save()
        return record

    def has_task(self, task_id: str) -> bool:
        return task_id in self.tasks

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        return self.tasks.get(task_id)

    def require_task(self, task_id: str) -> TaskRecord:
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")
        return task

    def delete_task(self, task_id: str) -> bool:
        if task_id not in self.tasks:
            return False
        del self.tasks[task_id]
        self.save()
        return True

    def list_tasks(self, status: Optional[str] = None) -> List[TaskRecord]:
        items = list(self.tasks.values())
        items.sort(key=lambda x: x.created_at, reverse=True)

        if status:
            items = [task for task in items if task.status == status]
        return items

    # ------------------------------------------------------------------
    # serialization helpers
    # ------------------------------------------------------------------
    def get_task_dict(self, task_id: str) -> Dict[str, Any]:
        return self.require_task(task_id).to_dict()

    def list_task_dicts(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return [task.to_dict() for task in self.list_tasks(status=status)]

    # ------------------------------------------------------------------
    # task state
    # ------------------------------------------------------------------
    def set_task_status(
        self,
        task_id: str,
        status: str,
        *,
        error: Optional[str] = None,
        result: Optional[str] = None,
    ) -> TaskRecord:
        task = self.require_task(task_id)
        task.status = status
        task.updated_at = _utc_now()

        if error is not None:
            task.error = error

        if result is not None:
            task.result = result

        self.append_history(
            task_id,
            "task_status_changed",
            {
                "status": status,
                "error": error,
                "result": result,
            },
            auto_save=False,
        )
        self.save()
        return task

    def set_task_result(self, task_id: str, result: str) -> TaskRecord:
        task = self.require_task(task_id)
        task.result = result
        task.updated_at = _utc_now()
        self.append_history(task_id, "task_result_set", {"result": result}, auto_save=False)
        self.save()
        return task

    def set_task_error(self, task_id: str, error: str) -> TaskRecord:
        task = self.require_task(task_id)
        task.error = error
        task.updated_at = _utc_now()
        self.append_history(task_id, "task_error_set", {"error": error}, auto_save=False)
        self.save()
        return task

    def update_task_metadata(self, task_id: str, patch: Dict[str, Any]) -> TaskRecord:
        task = self.require_task(task_id)
        task.metadata.update(deepcopy(patch))
        task.updated_at = _utc_now()
        self.append_history(task_id, "task_metadata_updated", {"patch": patch}, auto_save=False)
        self.save()
        return task

    # ------------------------------------------------------------------
    # steps
    # ------------------------------------------------------------------
    def set_steps(self, task_id: str, steps: List[Dict[str, Any] | TaskStep]) -> TaskRecord:
        task = self.require_task(task_id)

        normalized_steps: List[TaskStep] = []
        for index, item in enumerate(steps):
            if isinstance(item, TaskStep):
                step = item
            else:
                step = TaskStep(
                    step_id=item.get("step_id") or f"{task_id}-step-{index+1}",
                    title=item.get("title", f"step-{index+1}"),
                    description=item.get("description", ""),
                    status=item.get("status", "pending"),
                    result=item.get("result"),
                    error=item.get("error"),
                    tool=item.get("tool"),
                    tool_input=deepcopy(item.get("tool_input")) if item.get("tool_input") is not None else None,
                    metadata=deepcopy(item.get("metadata", {})),
                )
            normalized_steps.append(step)

        task.steps = normalized_steps
        task.current_step_index = 0
        task.status = "planned"
        task.updated_at = _utc_now()

        self.append_history(
            task_id,
            "task_steps_set",
            {
                "step_count": len(normalized_steps),
                "titles": [s.title for s in normalized_steps],
            },
            auto_save=False,
        )
        self.save()
        return task

    def add_step(self, task_id: str, step: Dict[str, Any] | TaskStep) -> TaskStep:
        task = self.require_task(task_id)

        if isinstance(step, TaskStep):
            new_step = step
        else:
            new_step = TaskStep(
                step_id=step.get("step_id") or f"{task_id}-step-{len(task.steps)+1}",
                title=step.get("title", f"step-{len(task.steps)+1}"),
                description=step.get("description", ""),
                status=step.get("status", "pending"),
                result=step.get("result"),
                error=step.get("error"),
                tool=step.get("tool"),
                tool_input=deepcopy(step.get("tool_input")) if step.get("tool_input") is not None else None,
                metadata=deepcopy(step.get("metadata", {})),
            )

        task.steps.append(new_step)
        task.updated_at = _utc_now()
        self.append_history(task_id, "task_step_added", {"step_id": new_step.step_id, "title": new_step.title}, auto_save=False)
        self.save()
        return new_step

    def get_current_step(self, task_id: str) -> Optional[TaskStep]:
        task = self.require_task(task_id)
        if not task.steps:
            return None
        if task.current_step_index < 0 or task.current_step_index >= len(task.steps):
            return None
        return task.steps[task.current_step_index]

    def get_step(self, task_id: str, step_index: int) -> Optional[TaskStep]:
        task = self.require_task(task_id)
        if step_index < 0 or step_index >= len(task.steps):
            return None
        return task.steps[step_index]

    def set_current_step_index(self, task_id: str, index: int) -> TaskRecord:
        task = self.require_task(task_id)
        if index < 0:
            index = 0
        task.current_step_index = index
        task.updated_at = _utc_now()
        self.append_history(task_id, "task_current_step_index_set", {"index": index}, auto_save=False)
        self.save()
        return task

    def mark_step_running(self, task_id: str, step_index: Optional[int] = None) -> TaskStep:
        task = self.require_task(task_id)
        index = task.current_step_index if step_index is None else step_index

        if index < 0 or index >= len(task.steps):
            raise ValueError(f"invalid step index: {index}")

        step = task.steps[index]
        step.status = "running"
        step.updated_at = _utc_now()

        task.status = "running"
        task.current_step_index = index
        task.updated_at = _utc_now()

        self.append_history(
            task_id,
            "step_running",
            {"step_index": index, "step_id": step.step_id, "title": step.title},
            auto_save=False,
        )
        self.save()
        return step

    def mark_step_done(
        self,
        task_id: str,
        result: Optional[str] = None,
        step_index: Optional[int] = None,
    ) -> TaskStep:
        task = self.require_task(task_id)
        index = task.current_step_index if step_index is None else step_index

        if index < 0 or index >= len(task.steps):
            raise ValueError(f"invalid step index: {index}")

        step = task.steps[index]
        step.status = "done"
        step.result = result
        step.error = None
        step.updated_at = _utc_now()

        task.updated_at = _utc_now()

        self.append_history(
            task_id,
            "step_done",
            {
                "step_index": index,
                "step_id": step.step_id,
                "title": step.title,
                "result": result,
            },
            auto_save=False,
        )
        self.save()
        return step

    def mark_step_failed(
        self,
        task_id: str,
        error: str,
        step_index: Optional[int] = None,
    ) -> TaskStep:
        task = self.require_task(task_id)
        index = task.current_step_index if step_index is None else step_index

        if index < 0 or index >= len(task.steps):
            raise ValueError(f"invalid step index: {index}")

        step = task.steps[index]
        step.status = "failed"
        step.error = error
        step.updated_at = _utc_now()

        task.status = "failed"
        task.error = error
        task.updated_at = _utc_now()

        self.append_history(
            task_id,
            "step_failed",
            {
                "step_index": index,
                "step_id": step.step_id,
                "title": step.title,
                "error": error,
            },
            auto_save=False,
        )
        self.save()
        return step

    def mark_step_skipped(
        self,
        task_id: str,
        reason: str = "",
        step_index: Optional[int] = None,
    ) -> TaskStep:
        task = self.require_task(task_id)
        index = task.current_step_index if step_index is None else step_index

        if index < 0 or index >= len(task.steps):
            raise ValueError(f"invalid step index: {index}")

        step = task.steps[index]
        step.status = "skipped"
        step.result = reason
        step.updated_at = _utc_now()

        task.updated_at = _utc_now()

        self.append_history(
            task_id,
            "step_skipped",
            {
                "step_index": index,
                "step_id": step.step_id,
                "title": step.title,
                "reason": reason,
            },
            auto_save=False,
        )
        self.save()
        return step

    def advance_step(self, task_id: str) -> TaskRecord:
        task = self.require_task(task_id)

        if not task.steps:
            task.status = "completed"
            task.updated_at = _utc_now()
            self.append_history(task_id, "task_completed_no_steps", {}, auto_save=False)
            self.save()
            return task

        next_index = task.current_step_index + 1

        if next_index >= len(task.steps):
            task.current_step_index = len(task.steps)
            task.status = "completed"
            task.updated_at = _utc_now()
            self.append_history(task_id, "task_completed", {}, auto_save=False)
        else:
            task.current_step_index = next_index
            task.status = "queued"
            task.updated_at = _utc_now()
            self.append_history(task_id, "task_advanced", {"next_step_index": next_index}, auto_save=False)

        self.save()
        return task

    def reset_steps_to_pending(self, task_id: str, from_index: int = 0) -> TaskRecord:
        task = self.require_task(task_id)

        for idx in range(max(0, from_index), len(task.steps)):
            step = task.steps[idx]
            step.status = "pending"
            step.result = None
            step.error = None
            step.updated_at = _utc_now()

        task.status = "queued"
        task.current_step_index = max(0, from_index)
        task.error = None
        task.updated_at = _utc_now()

        self.append_history(
            task_id,
            "task_steps_reset_to_pending",
            {"from_index": from_index},
            auto_save=False,
        )
        self.save()
        return task

    def all_steps_done(self, task_id: str) -> bool:
        task = self.require_task(task_id)
        if not task.steps:
            return True
        return all(step.status in ("done", "skipped") for step in task.steps)

    # ------------------------------------------------------------------
    # history
    # ------------------------------------------------------------------
    def append_history(
        self,
        task_id: str,
        event: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        auto_save: bool = True,
    ) -> Dict[str, Any]:
        task = self.require_task(task_id)
        item = {
            "time": _utc_now(),
            "event": event,
            "payload": deepcopy(payload or {}),
        }
        task.history.append(item)
        task.updated_at = _utc_now()

        if auto_save:
            self.save()

        return item

    # ------------------------------------------------------------------
    # compatibility helpers
    # ------------------------------------------------------------------
    def enqueue_task(self, task_id: str) -> TaskRecord:
        return self.set_task_status(task_id, "queued")

    def start_task(self, task_id: str) -> TaskRecord:
        return self.set_task_status(task_id, "running")

    def complete_task(self, task_id: str, result: Optional[str] = None) -> TaskRecord:
        return self.set_task_status(task_id, "completed", result=result)

    def fail_task(self, task_id: str, error: str) -> TaskRecord:
        return self.set_task_status(task_id, "failed", error=error)

    def pause_task(self, task_id: str) -> TaskRecord:
        return self.set_task_status(task_id, "paused")

    def cancel_task(self, task_id: str) -> TaskRecord:
        return self.set_task_status(task_id, "cancelled")


# ----------------------------------------------------------------------
# backward-compatible alias
# ----------------------------------------------------------------------
class TaskManager(TaskRepository):
    """
    先保留舊名稱，避免其他檔案 import TaskManager 直接炸掉。
    但這個類別現在本質上只是 repository，不再承擔 planner 責任。
    """
    pass