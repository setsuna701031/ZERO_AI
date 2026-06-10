from __future__ import annotations

"""Read-only deterministic queries over persisted goals."""

import copy
from typing import Any

from core.goals.goal_contract import TERMINAL_GOAL_STATUSES
from core.goals.goal_repository import GoalRepository


class GoalQuery:
    def __init__(self, repository: GoalRepository) -> None:
        self.repository = repository

    def find_active_goals(self) -> list[dict[str, Any]]:
        return [goal for goal in self.repository.list_goals() if goal.get("status") == "active"]

    def find_blocked_goals(self) -> list[dict[str, Any]]:
        return [goal for goal in self.repository.list_goals() if goal.get("status") == "blocked"]

    def find_recent_goals(self, limit: int = 10) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return sorted(
            self.repository.list_goals(),
            key=lambda goal: (str(goal.get("updated_at") or ""), str(goal.get("goal_id") or "")),
            reverse=True,
        )[:limit]

    def find_goal_history(self, goal_id: str) -> list[dict[str, Any]]:
        return self.repository.list_history(goal_id)

    def find_resume_candidates(self) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for goal in self.repository.list_goals():
            if goal.get("status") in TERMINAL_GOAL_STATUSES:
                continue
            resume_point = self.repository.get_resume_point(str(goal.get("goal_id") or ""))
            if resume_point is not None:
                candidate = copy.deepcopy(resume_point)
                candidate["goal_id"] = goal["goal_id"]
                candidate["goal_status"] = goal["status"]
                candidate["goal_updated_at"] = goal["updated_at"]
                candidates.append(candidate)
        return candidates


__all__ = ["GoalQuery"]
