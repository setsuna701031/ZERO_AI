from __future__ import annotations

"""Derived lifecycle state for engineering portfolios.

EngineeringPortfolioState owns only portfolio lifecycle evaluation and progress
summaries. It reads portfolio records and goal snapshots supplied by callers;
it does not persist data, execute goals, schedule work, run loops, or call
runtime owners.
"""

import copy
import time
from typing import Any, Mapping, Sequence


ENGINEERING_PORTFOLIO_STATE_SCHEMA = "zero.engineering_portfolio_state.v1"
ENGINEERING_PORTFOLIO_SUMMARY_SCHEMA = "zero.engineering_portfolio_summary.v1"

PORTFOLIO_STATES = {"active", "paused", "blocked", "completed", "archived"}
COMPLETED_GOAL_STATUSES = {"complete", "completed"}
BLOCKED_GOAL_STATUSES = {"blocked"}
TERMINAL_GOAL_STATUSES = COMPLETED_GOAL_STATUSES | BLOCKED_GOAL_STATUSES | {"cancelled", "canceled"}
MANUAL_PORTFOLIO_STATES = {"paused", "archived"}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> list[Any]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        return []
    return list(value)


def _goal_id(goal: Mapping[str, Any]) -> str:
    return _clean_text(goal.get("goal_id") or goal.get("task_id") or goal.get("package_id"))


def _goal_status(goal: Mapping[str, Any]) -> str:
    return _clean_text(goal.get("status"), "pending").lower()


def _manual_portfolio_state(portfolio: Mapping[str, Any]) -> str:
    metadata = _as_mapping(portfolio.get("metadata"))
    candidates = (
        portfolio.get("portfolio_state"),
        portfolio.get("lifecycle_state"),
        portfolio.get("state"),
        portfolio.get("status"),
        metadata.get("portfolio_state"),
        metadata.get("lifecycle_state"),
        metadata.get("state"),
        metadata.get("status"),
    )
    for candidate in candidates:
        state = _clean_text(candidate).lower()
        if state in MANUAL_PORTFOLIO_STATES:
            return state
    return ""


def _clean_goal_refs(portfolio: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for item in _as_sequence(portfolio.get("goal_ids")):
        goal_id = _clean_text(item)
        if goal_id and goal_id not in seen:
            refs.append(goal_id)
            seen.add(goal_id)
    return refs


def _goals_by_id(goals: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    if isinstance(goals, Mapping):
        items = goals.values()
    else:
        items = goals

    records: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        goal = _as_mapping(item)
        goal_id = _goal_id(goal)
        if goal_id:
            records[goal_id] = goal
    return records


class EngineeringPortfolioState:
    """Evaluate lifecycle state and progress for one portfolio snapshot."""

    def evaluate_portfolio_state(
        self,
        portfolio: Mapping[str, Any],
        goals: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
    ) -> str:
        manual_state = _manual_portfolio_state(portfolio)
        if manual_state:
            return manual_state

        progress = self.calculate_progress(portfolio, goals)
        goal_count = int(progress["goal_count"])
        if goal_count > 0 and progress["completed_goal_count"] == goal_count:
            return "completed"
        if int(progress["active_goal_count"]) > 0:
            return "active"
        if goal_count > 0 and progress["blocked_goal_count"] == goal_count:
            return "blocked"
        return "active"

    def calculate_progress(
        self,
        portfolio: Mapping[str, Any],
        goals: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        goal_refs = _clean_goal_refs(portfolio)
        goal_records = _goals_by_id(goals)

        completed_goal_count = 0
        blocked_goal_count = 0
        active_goal_count = 0

        for goal_id in goal_refs:
            goal = goal_records.get(goal_id)
            if goal is None:
                continue
            status = _goal_status(goal)
            if status in COMPLETED_GOAL_STATUSES:
                completed_goal_count += 1
            elif status in BLOCKED_GOAL_STATUSES:
                blocked_goal_count += 1
            elif status not in TERMINAL_GOAL_STATUSES:
                active_goal_count += 1

        goal_count = len(goal_refs)
        completion_ratio = completed_goal_count / goal_count if goal_count else 0.0
        return {
            "goal_count": goal_count,
            "completed_goal_count": completed_goal_count,
            "blocked_goal_count": blocked_goal_count,
            "active_goal_count": active_goal_count,
            "completion_ratio": completion_ratio,
        }

    def summarize_portfolio(
        self,
        portfolio: Mapping[str, Any],
        goals: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        target_portfolio = _as_mapping(portfolio)
        goal_refs = _clean_goal_refs(target_portfolio)
        goal_records = _goals_by_id(goals)
        progress = self.calculate_progress(target_portfolio, goal_records)
        state = self.evaluate_portfolio_state(target_portfolio, goal_records)

        goal_summaries: list[dict[str, Any]] = []
        missing_goal_ids: list[str] = []
        for goal_id in goal_refs:
            goal = goal_records.get(goal_id)
            if goal is None:
                missing_goal_ids.append(goal_id)
                goal_summaries.append({"goal_id": goal_id, "status": "missing", "runnable": False})
                continue
            status = _goal_status(goal)
            goal_summaries.append(
                {
                    "goal_id": goal_id,
                    "status": status,
                    "summary": _clean_text(goal.get("summary")),
                    "runnable": status not in TERMINAL_GOAL_STATUSES,
                }
            )

        return {
            "schema": ENGINEERING_PORTFOLIO_SUMMARY_SCHEMA,
            "ok": True,
            "portfolio_id": _clean_text(target_portfolio.get("portfolio_id") or target_portfolio.get("id")),
            "state": state,
            **progress,
            "goals": goal_summaries,
            "missing_goal_ids": missing_goal_ids,
            "updated_at": time.time(),
        }


__all__ = [
    "ENGINEERING_PORTFOLIO_STATE_SCHEMA",
    "ENGINEERING_PORTFOLIO_SUMMARY_SCHEMA",
    "PORTFOLIO_STATES",
    "EngineeringPortfolioState",
]
