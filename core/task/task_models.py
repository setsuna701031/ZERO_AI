# core/task/task_models.py

from typing import Any, Dict, List, Optional
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
            step_id=data.get("step_id"),
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

    def add_history(self, from_status: Optional[str], to_status: str, reason: str) -> None:
        self.history.append({
            "from": from_status,
            "to": to_status,
            "reason": reason,
            "timestamp": now_iso(),
        })
        self.updated_at = now_iso()

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
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRecord":
        steps_data = data.get("steps", [])
        steps = [StepRecord.from_dict(s) for s in steps_data]

        return cls(
            task_id=data.get("task_id"),
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
        )