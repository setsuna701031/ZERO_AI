from __future__ import annotations

"""Policy controls for passive goal execution planning."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GoalExecutionPolicy:
    allow_create_task_from_subgoal: bool = True
    allow_resume_task_from_resume_point: bool = False
    require_review_before_create_task: bool = False
    require_review_before_resume: bool = True
    require_review_before_complete_goal: bool = True
    max_execution_plans_per_cycle: int = 1

    def __post_init__(self) -> None:
        if int(self.max_execution_plans_per_cycle) <= 0:
            raise ValueError("max_execution_plans_per_cycle_must_be_positive")
        object.__setattr__(self, "max_execution_plans_per_cycle", int(self.max_execution_plans_per_cycle))


__all__ = ["GoalExecutionPolicy"]
