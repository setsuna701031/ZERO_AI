from __future__ import annotations

"""Scheduling layer for engineering goals.

EngineeringGoalScheduler owns scheduling decisions only. It updates scheduling
metadata in returned records, asks EngineeringGoalPortfolio to select runnable
goals, and delegates selected-goal routing to the existing planning-loop
interface supplied by the caller.
"""

import copy
import time
from typing import Any, Mapping, Sequence

from core.tasks.engineering_goal_portfolio import EngineeringGoalPortfolio, EngineeringGoalRecord


ENGINEERING_GOAL_SCHEDULER_SCHEMA = "zero.engineering_goal_scheduler.v1"
SCHEDULER_DECISION_SCHEMA = "zero.engineering_goal_scheduler.decision.v1"

SCHEDULER_HELD_STATUSES = {"paused", "deferred"}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _goal_dict(value: EngineeringGoalRecord | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, EngineeringGoalRecord):
        return value.as_dict()
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    raise ValueError("engineering_goal_scheduler_records_must_be_mappings")


def _priority(value: Mapping[str, Any]) -> float:
    try:
        return float(value.get("priority") or 0)
    except (TypeError, ValueError):
        return 0.0


def _created_at(value: Mapping[str, Any]) -> float:
    try:
        return float(value.get("created_at") or 0)
    except (TypeError, ValueError):
        return 0.0


def _goal_id(value: Mapping[str, Any]) -> str:
    return _clean_text(value.get("goal_id") or value.get("task_id") or value.get("package_id"))


def _decision(
    *,
    selected_goal_id: str,
    action: str,
    reason: str,
    skipped_goals: list[dict[str, Any]] | None = None,
    deferred_goals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEDULER_DECISION_SCHEMA,
        "selected_goal_id": selected_goal_id,
        "action": action,
        "reason": reason,
        "skipped_goals": copy.deepcopy(skipped_goals or []),
        "deferred_goals": copy.deepcopy(deferred_goals or []),
    }


class EngineeringGoalScheduler:
    """Determines when and in what order engineering goals should run."""

    def __init__(self, *, portfolio: EngineeringGoalPortfolio | Any | None = None) -> None:
        self.portfolio = portfolio or EngineeringGoalPortfolio()

    def schedule_next_goal(
        self,
        goals: Sequence[EngineeringGoalRecord | Mapping[str, Any]],
    ) -> dict[str, Any]:
        records = [_goal_dict(goal) for goal in goals]
        active_goals, scheduler_skipped, deferred_goals = self._schedulable_records(records)
        portfolio_decision = self.portfolio.decide_next_goal(active_goals)
        selected_goal_id = _clean_text(portfolio_decision.get("selected_goal_id"))
        skipped_goals = [
            *copy.deepcopy(portfolio_decision.get("skipped_goals") or []),
            *scheduler_skipped,
        ]
        scheduler_decision = _decision(
            selected_goal_id=selected_goal_id,
            action="schedule_next_goal" if selected_goal_id else "no_runnable_goal",
            reason=_clean_text(portfolio_decision.get("reason"), "no_runnable_goals_available"),
            skipped_goals=skipped_goals,
            deferred_goals=deferred_goals,
        )
        return {
            "schema": ENGINEERING_GOAL_SCHEDULER_SCHEMA,
            "ok": bool(selected_goal_id),
            "mode": "engineering_goal_scheduler",
            "scheduler_decision": scheduler_decision,
            "portfolio_decision": portfolio_decision,
            "goals": records,
            "execution_path": {
                "scheduler_schedules_only": True,
                "portfolio_selects_only": True,
                "direct_execution": False,
                "existing_planning_loop_reused": False,
                "new_execution_path": False,
            },
        }

    def run_next_goal(
        self,
        goals: Sequence[EngineeringGoalRecord | Mapping[str, Any]],
        *,
        planning_loop: Any,
    ) -> dict[str, Any]:
        records = [_goal_dict(goal) for goal in goals]
        active_goals, scheduler_skipped, deferred_goals = self._schedulable_records(records)
        portfolio_decision = self.portfolio.decide_next_goal(active_goals)
        selected_goal_id = _clean_text(portfolio_decision.get("selected_goal_id"))
        skipped_goals = [
            *copy.deepcopy(portfolio_decision.get("skipped_goals") or []),
            *scheduler_skipped,
        ]
        scheduler_decision = _decision(
            selected_goal_id=selected_goal_id,
            action="run_next_goal" if selected_goal_id else "no_runnable_goal",
            reason=_clean_text(portfolio_decision.get("reason"), "no_runnable_goals_available"),
            skipped_goals=skipped_goals,
            deferred_goals=deferred_goals,
        )

        if not selected_goal_id:
            return {
                "schema": ENGINEERING_GOAL_SCHEDULER_SCHEMA,
                "ok": False,
                "mode": "engineering_goal_scheduler",
                "scheduler_decision": scheduler_decision,
                "portfolio_decision": portfolio_decision,
                "planning_result": {},
                "goals": records,
                "execution_path": {
                    "scheduler_schedules_only": True,
                    "portfolio_selects_only": True,
                    "direct_execution": False,
                    "existing_planning_loop_reused": False,
                    "new_execution_path": False,
                },
            }

        portfolio_result = self.portfolio.route_selected_goal(active_goals, planning_loop=planning_loop)
        return {
            "schema": ENGINEERING_GOAL_SCHEDULER_SCHEMA,
            "ok": bool(_as_mapping(portfolio_result).get("ok")),
            "mode": "engineering_goal_scheduler",
            "scheduler_decision": scheduler_decision,
            "portfolio_decision": portfolio_decision,
            "portfolio_result": copy.deepcopy(dict(portfolio_result)) if isinstance(portfolio_result, Mapping) else {},
            "planning_result": copy.deepcopy(_as_mapping(_as_mapping(portfolio_result).get("planning_result"))),
            "goals": records,
            "execution_path": {
                "scheduler_schedules_only": True,
                "portfolio_selects_only": True,
                "direct_execution": False,
                "existing_planning_loop_reused": True,
                "new_execution_path": False,
            },
        }

    def pause_goal(
        self,
        goals: Sequence[EngineeringGoalRecord | Mapping[str, Any]],
        goal_id: str,
        *,
        reason: str = "goal_paused",
    ) -> dict[str, Any]:
        return self._set_goal_status(goals, goal_id, action="pause_goal", status="paused", reason=reason)

    def resume_goal(
        self,
        goals: Sequence[EngineeringGoalRecord | Mapping[str, Any]],
        goal_id: str,
        *,
        reason: str = "goal_resumed",
    ) -> dict[str, Any]:
        return self._set_goal_status(goals, goal_id, action="resume_goal", status="pending", reason=reason)

    def cancel_goal(
        self,
        goals: Sequence[EngineeringGoalRecord | Mapping[str, Any]],
        goal_id: str,
        *,
        reason: str = "goal_cancelled",
    ) -> dict[str, Any]:
        return self._set_goal_status(goals, goal_id, action="cancel_goal", status="cancelled", reason=reason)

    def defer_goal(
        self,
        goals: Sequence[EngineeringGoalRecord | Mapping[str, Any]],
        goal_id: str,
        *,
        reason: str = "goal_deferred",
        deferred_until: Any = "",
    ) -> dict[str, Any]:
        return self._set_goal_status(
            goals,
            goal_id,
            action="defer_goal",
            status="deferred",
            reason=reason,
            extra={"deferred_until": deferred_until},
        )

    def _set_goal_status(
        self,
        goals: Sequence[EngineeringGoalRecord | Mapping[str, Any]],
        goal_id: str,
        *,
        action: str,
        status: str,
        reason: str,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        records = [_goal_dict(goal) for goal in goals]
        target_goal_id = _clean_text(goal_id)
        updated = False
        for record in records:
            if _goal_id(record) != target_goal_id:
                continue
            record["status"] = status
            record["updated_at"] = time.time()
            schedule_refs = _as_mapping(record.get("schedule_refs"))
            schedule_refs.update({"last_scheduler_action": action, "last_scheduler_reason": reason})
            schedule_refs.update(copy.deepcopy(dict(extra or {})))
            record["schedule_refs"] = schedule_refs
            updated = True
            break

        _, skipped_goals, deferred_goals = self._schedulable_records(records)
        scheduler_decision = _decision(
            selected_goal_id=target_goal_id if updated else "",
            action=action if updated else "goal_not_found",
            reason=reason if updated else "goal_not_found",
            skipped_goals=skipped_goals,
            deferred_goals=deferred_goals,
        )
        return {
            "schema": ENGINEERING_GOAL_SCHEDULER_SCHEMA,
            "ok": updated,
            "mode": "engineering_goal_scheduler",
            "scheduler_decision": scheduler_decision,
            "goals": records,
            "execution_path": {
                "scheduler_schedules_only": True,
                "portfolio_selects_only": False,
                "direct_execution": False,
                "existing_planning_loop_reused": False,
                "new_execution_path": False,
            },
        }

    def _schedulable_records(
        self,
        records: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        active_goals: list[dict[str, Any]] = []
        skipped_goals: list[dict[str, Any]] = []
        deferred_goals: list[dict[str, Any]] = []
        for record in sorted(records, key=lambda item: (-_priority(item), _created_at(item), _goal_id(item))):
            status = _clean_text(record.get("status"), "pending").lower()
            goal_id = _goal_id(record)
            if status == "paused":
                skipped_goals.append({"goal_id": goal_id, "status": status, "reason": "goal_status_paused"})
                continue
            if status == "deferred":
                schedule_refs = _as_mapping(record.get("schedule_refs"))
                deferred_goals.append(
                    {
                        "goal_id": goal_id,
                        "status": status,
                        "reason": "goal_status_deferred",
                        "deferred_until": schedule_refs.get("deferred_until", ""),
                    }
                )
                continue
            active_goals.append(copy.deepcopy(record))
        return active_goals, skipped_goals, deferred_goals


__all__ = [
    "ENGINEERING_GOAL_SCHEDULER_SCHEMA",
    "SCHEDULER_DECISION_SCHEMA",
    "EngineeringGoalScheduler",
]
