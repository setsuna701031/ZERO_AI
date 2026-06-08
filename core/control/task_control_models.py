from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class TaskSubmission:
    title: str
    instruction: str
    task_type: str = "engineering_task"
    mode: str = ""

    def normalized(self) -> "TaskSubmission":
        return TaskSubmission(
            title=str(self.title or "").strip(),
            instruction=str(self.instruction or "").strip(),
            task_type=str(self.task_type or "engineering_task").strip() or "engineering_task",
            mode=str(self.mode or "").strip(),
        )

    def validate(self) -> str:
        normalized = self.normalized()
        if not normalized.title:
            return "title is required"
        if not normalized.instruction:
            return "instruction is required"
        return ""

    def scheduler_kwargs(self) -> Dict[str, Any]:
        normalized = self.normalized()
        return {
            "goal": normalized.instruction,
            "title": normalized.title,
            "task_type": normalized.task_type,
            "mode": normalized.mode,
            "source": "task_control_api",
            "control_request": {
                "title": normalized.title,
                "mode": normalized.mode,
                "task_type": normalized.task_type,
            },
        }


__all__ = ["TaskSubmission"]
