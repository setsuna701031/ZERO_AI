from __future__ import annotations
from typing import Any, Mapping

EXCLUDED_GOAL_STATUSES = {"completed", "cancelled", "stopped", "paused", "failed", "blocked"}

def eligible_goals(goals: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted((dict(goal) for goal in goals if goal.get("goal_status") not in EXCLUDED_GOAL_STATUSES), key=lambda goal: (str(goal.get("created_at") or ""), str(goal["goal_id"])))

def select_round_robin(goals: list[Mapping[str, Any]], *, cursor: int, limit: int) -> tuple[list[dict[str, Any]], int]:
    eligible = eligible_goals(goals)
    if not eligible: return [], 0
    start = max(0, int(cursor)) % len(eligible); rotated = eligible[start:] + eligible[:start]; selected = rotated[:min(limit, len(rotated))]
    return selected, (start + max(1, len(selected))) % len(eligible)

__all__ = ["EXCLUDED_GOAL_STATUSES", "eligible_goals", "select_round_robin"]
