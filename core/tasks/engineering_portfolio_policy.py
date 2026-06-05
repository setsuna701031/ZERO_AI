from __future__ import annotations

"""Selection policy for engineering portfolios.

EngineeringPortfolioPolicy owns only deterministic goal selection rules. It
does not load data, persist data, execute goals, schedule work, use memory, or
call runtime owners.
"""

import copy
import time
from typing import Any, Mapping, Sequence


ENGINEERING_PORTFOLIO_POLICY_SCHEMA = "zero.engineering_portfolio_policy.v1"
ENGINEERING_PORTFOLIO_POLICY_SELECTION_SCHEMA = "zero.engineering_portfolio_policy.selection.v1"

COMPLETED_STATUSES = {"complete", "completed"}
BLOCKED_STATUSES = {"blocked"}
CANCELLED_STATUSES = {"cancelled", "canceled"}
PAUSED_STATUSES = {"paused"}
RUNNABLE_STATUSES = {"active", "pending", "in_progress"}
MISSING_STATUSES = {"missing"}
SKIPPED_STATES = {"completed", "blocked", "cancelled", "paused", "missing"}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _goal_id(goal: Mapping[str, Any]) -> str:
    return _clean_text(goal.get("goal_id") or goal.get("task_id") or goal.get("package_id"))


class EngineeringPortfolioPolicy:
    """Deterministically classify and select portfolio goals."""

    def classify_goal_state(self, goal: Mapping[str, Any]) -> str:
        if not isinstance(goal, Mapping) or not _goal_id(goal):
            return "missing"
        status = _clean_text(goal.get("status"), "pending").lower()
        if status in MISSING_STATUSES:
            return "missing"
        if status in COMPLETED_STATUSES:
            return "completed"
        if status in BLOCKED_STATUSES:
            return "blocked"
        if status in CANCELLED_STATUSES:
            return "cancelled"
        if status in PAUSED_STATUSES:
            return "paused"
        if status in RUNNABLE_STATUSES:
            return "runnable"
        return "runnable"

    def is_runnable_goal(self, goal: Mapping[str, Any]) -> bool:
        return self.classify_goal_state(goal) == "runnable"

    def explain_skip_reason(self, goal: Mapping[str, Any]) -> str:
        state = self.classify_goal_state(goal)
        if state == "completed":
            return "completed_goal"
        if state == "blocked":
            return "blocked_goal"
        if state == "cancelled":
            return "cancelled_goal"
        if state == "paused":
            return "paused_goal"
        if state == "missing":
            return "goal_not_found"
        return ""

    def select_next_goal(self, goals: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        summary = self.build_selection_summary(goals)
        selected_goal = _as_mapping(summary.get("selected_goal"))
        return {
            "schema": ENGINEERING_PORTFOLIO_POLICY_SELECTION_SCHEMA,
            "ok": bool(selected_goal),
            "decision": "selected" if selected_goal else "no_runnable_goal",
            "reason": "first_runnable_goal" if selected_goal else "no_runnable_goal",
            "selected_goal_id": _goal_id(selected_goal),
            "selected_goal": selected_goal,
            "skipped_goals": copy.deepcopy(summary["skipped_goals"]),
            "selection_summary": summary,
            "updated_at": time.time(),
        }

    def build_selection_summary(self, goals: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        selected_goal: dict[str, Any] = {}
        skipped_goals: list[dict[str, Any]] = []
        runnable_goal_ids: list[str] = []

        for index, item in enumerate(goals):
            goal = _as_mapping(item)
            goal_id = _goal_id(goal)
            state = self.classify_goal_state(goal)
            if state == "runnable":
                runnable_goal_ids.append(goal_id)
                if not selected_goal:
                    selected_goal = goal
                continue
            skipped_goals.append(
                {
                    "goal_id": goal_id,
                    "status": _clean_text(goal.get("status")),
                    "state": state,
                    "reason": self.explain_skip_reason(goal),
                    "index": index,
                }
            )

        return {
            "schema": ENGINEERING_PORTFOLIO_POLICY_SCHEMA,
            "selected_goal_id": _goal_id(selected_goal),
            "selected_goal": selected_goal,
            "runnable_goal_ids": runnable_goal_ids,
            "skipped_goals": skipped_goals,
            "goal_count": len(goals),
            "runnable_goal_count": len(runnable_goal_ids),
            "skipped_goal_count": len(skipped_goals),
            "deterministic_ref_order": True,
            "priority_algorithm": False,
            "updated_at": time.time(),
        }


__all__ = [
    "ENGINEERING_PORTFOLIO_POLICY_SCHEMA",
    "ENGINEERING_PORTFOLIO_POLICY_SELECTION_SCHEMA",
    "EngineeringPortfolioPolicy",
]
