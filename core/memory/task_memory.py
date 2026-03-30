from __future__ import annotations

import json
import time
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now().isoformat()


@dataclass
class TaskStep:
    id: str
    title: str
    tool: str
    input: Dict[str, Any]
    status: str = "pending"
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 1
    index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskStep":
        return cls(
            id=data["id"],
            title=data["title"],
            tool=data["tool"],
            input=data.get("input", {}) or {},
            status=data.get("status", "pending"),
            output=data.get("output"),
            error=data.get("error"),
            retries=int(data.get("retries", 0)),
            max_retries=int(data.get("max_retries", 1)),
            index=int(data.get("index", 0)),
        )


@dataclass
class Task:
    id: str
    title: str
    goal: str
    status: str = "pending"
    workspace: str = ""
    steps: List[TaskStep] = field(default_factory=list)
    current_step_index: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["steps"] = [step.to_dict() for step in self.steps]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(
            id=data["id"],
            title=data.get("title", ""),
            goal=data.get("goal", ""),
            status=data.get("status", "pending"),
            workspace=data.get("workspace", ""),
            steps=[TaskStep.from_dict(step) for step in data.get("steps", [])],
            current_step_index=int(data.get("current_step_index", 0)),
            result=data.get("result"),
            error=data.get("error"),
            metadata=data.get("metadata", {}) or {},
            history=data.get("history", []) or [],
        )


class TaskManager:
    def __init__(self, base_dir: str = "workspace/tasks") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.tasks: Dict[str, Task] = {}
        self._load_existing_tasks()

    def _load_existing_tasks(self) -> None:
        for task_file in self.base_dir.glob("*/task.json"):
            try:
                data = json.loads(task_file.read_text(encoding="utf-8"))
                task = Task.from_dict(data)
                self.tasks[task.id] = task
            except Exception:
                continue

    def create_task(self, goal: str, title: Optional[str] = None) -> Task:
        task_id = f"task_{int(time.time())}"
        workspace = str(self.base_dir / task_id)

        task = Task(
            id=task_id,
            title=title or goal,
            goal=goal,
            status="pending",
            workspace=workspace,
            steps=[],
            current_step_index=0,
            result=None,
            error=None,
            metadata={},
            history=[],
        )

        Path(workspace).mkdir(parents=True, exist_ok=True)
        self.tasks[task_id] = task
        self.add_history(task_id, None, "pending", "task created")
        self.save_task(task_id)
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    def list_tasks(self) -> List[Task]:
        return list(self.tasks.values())

    def get_pending_tasks(self) -> List[Task]:
        return [task for task in self.tasks.values() if task.status == "pending"]

    def save_task(self, task_id: str) -> None:
        task = self.get_task(task_id)
        if task is None:
            return

        task_dir = Path(task.workspace)
        task_dir.mkdir(parents=True, exist_ok=True)
        task_file = task_dir / "task.json"
        task_file.write_text(
            json.dumps(task.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_history(
        self,
        task_id: str,
        from_status: Optional[str],
        to_status: str,
        reason: str,
    ) -> None:
        task = self.get_task(task_id)
        if task is None:
            return

        task.history.append(
            {
                "from": from_status,
                "to": to_status,
                "reason": reason,
                "timestamp": now_iso(),
            }
        )

    def set_status(self, task_id: str, new_status: str, reason: str) -> None:
        task = self.get_task(task_id)
        if task is None:
            return

        old_status = task.status
        task.status = new_status
        self.add_history(task_id, old_status, new_status, reason)
        self.save_task(task_id)

    def set_steps(self, task_id: str, steps: List[TaskStep]) -> None:
        task = self.get_task(task_id)
        if task is None:
            return

        task.steps = steps
        task.current_step_index = 0
        self.save_task(task_id)

    def update_step(self, task_id: str, step_index: int, step: TaskStep) -> None:
        task = self.get_task(task_id)
        if task is None:
            return

        if 0 <= step_index < len(task.steps):
            task.steps[step_index] = step
            self.save_task(task_id)

    def set_current_step_index(self, task_id: str, index: int) -> None:
        task = self.get_task(task_id)
        if task is None:
            return

        task.current_step_index = index
        self.save_task(task_id)

    def complete_task(self, task_id: str, result: Dict[str, Any]) -> None:
        task = self.get_task(task_id)
        if task is None:
            return

        task.result = deepcopy(result)
        task.error = None
        self.set_status(task_id, "completed", "task completed")
        self.save_task(task_id)

    def fail_task(self, task_id: str, error: str) -> None:
        task = self.get_task(task_id)
        if task is None:
            return

        task.error = error
        self.set_status(task_id, "failed", "task failed")
        self.save_task(task_id)

    def set_metadata(self, task_id: str, key: str, value: Any) -> None:
        task = self.get_task(task_id)
        if task is None:
            return

        task.metadata[key] = value
        self.save_task(task_id)

    def build_plan_for_goal(self, goal: str) -> List[TaskStep]:
        """
        這裡先保留最小可用規則規劃器。
        目的是讓你能快速測：
        - demo_fail_first  -> 首次失敗後成功
        - demo_always_fail -> 永久失敗
        - 其他             -> 正常成功
        """
        goal_text = (goal or "").strip()

        if "永久失敗" in goal_text or "always fail" in goal_text.lower():
            return [
                TaskStep(
                    id="step_1",
                    title="原始任務步驟",
                    tool="workspace",
                    input={"action": "mkdir", "path": "demo_always_fail"},
                    status="pending",
                    retries=0,
                    max_retries=1,
                    index=0,
                )
            ]

        if "失敗" in goal_text or "fail" in goal_text.lower():
            return [
                TaskStep(
                    id="step_1",
                    title="原始任務步驟",
                    tool="workspace",
                    input={"action": "mkdir", "path": "demo_fail_first"},
                    status="pending",
                    retries=0,
                    max_retries=1,
                    index=0,
                )
            ]

        return [
            TaskStep(
                id="step_1",
                title="原始任務步驟",
                tool="workspace",
                input={"action": "mkdir", "path": "demo_ok"},
                status="pending",
                retries=0,
                max_retries=1,
                index=0,
            )
        ]