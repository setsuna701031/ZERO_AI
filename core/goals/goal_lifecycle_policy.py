from __future__ import annotations

"""Explicit policy controls for passive goal orchestration decisions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GoalLifecyclePolicy:
    allow_auto_start_next_subgoal: bool = True
    allow_resume_blocked_subgoal: bool = False
    require_review_before_resume: bool = True
    require_review_before_goal_completion: bool = True
    max_subgoals_per_cycle: int = 1

    def __post_init__(self) -> None:
        if int(self.max_subgoals_per_cycle) <= 0:
            raise ValueError("max_subgoals_per_cycle_must_be_positive")
        object.__setattr__(self, "max_subgoals_per_cycle", int(self.max_subgoals_per_cycle))


__all__ = ["GoalLifecyclePolicy"]
