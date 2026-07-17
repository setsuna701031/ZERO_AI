from __future__ import annotations

"""Multi-goal selection for engineering planning.

EngineeringGoalPortfolio owns only portfolio-level selection. It does not
plan, execute, persist memory, or mutate lifecycle state; selected goal
payloads are delegated to the existing EngineeringPlanningLoop entrypoint.
"""

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


ENGINEERING_GOAL_PORTFOLIO_SCHEMA = "zero.engineering_goal_portfolio.v1"
PORTFOLIO_DECISION_SCHEMA = "zero.engineering_goal_portfolio.decision.v1"

TERMINAL_NON_RUNNABLE_STATUSES = {"completed", "blocked", "cancelled"}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class EngineeringGoalRecord:
    """Portfolio-visible metadata for one engineering goal."""

    goal_id: str
    priority: float = 0.0
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_result_summary: str = ""
    blocked_reason: str = ""
    planning_refs: dict[str, Any] = field(default_factory=dict)
    lifecycle_refs: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EngineeringGoalRecord":
        goal_id = _clean_text(value.get("goal_id") or value.get("task_id") or value.get("package_id"))
        if not goal_id:
            raise ValueError("engineering_goal_record_requires_goal_id")
        return cls(
            goal_id=goal_id,
            priority=_as_float(value.get("priority")),
            status=_clean_text(value.get("status"), "pending").lower(),
            created_at=_as_float(value.get("created_at"), 0.0),
            updated_at=_as_float(value.get("updated_at"), 0.0),
            last_result_summary=_clean_text(value.get("last_result_summary")),
            blocked_reason=_clean_text(value.get("blocked_reason")),
            planning_refs=_as_mapping(value.get("planning_refs")),
            lifecycle_refs=_as_mapping(value.get("lifecycle_refs")),
            payload=copy.deepcopy(_as_mapping(value.get("payload") or value.get("planning_payload"))),
        )

    def as_payload(self) -> dict[str, Any]:
        payload = copy.deepcopy(self.payload)
        payload.setdefault("goal_id", self.goal_id)
        payload.setdefault("task_id", self.goal_id)
        payload.setdefault("package_id", self.goal_id)
        payload.setdefault("task_type", "engineering_task")
        return payload

    def as_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_result_summary": self.last_result_summary,
            "blocked_reason": self.blocked_reason,
            "planning_refs": copy.deepcopy(self.planning_refs),
            "lifecycle_refs": copy.deepcopy(self.lifecycle_refs),
            "payload": copy.deepcopy(self.payload),
        }


def _record(value: EngineeringGoalRecord | Mapping[str, Any]) -> EngineeringGoalRecord:
    if isinstance(value, EngineeringGoalRecord):
        return value
    if isinstance(value, Mapping):
        return EngineeringGoalRecord.from_mapping(value)
    raise ValueError("engineering_goal_portfolio_records_must_be_mappings")


class EngineeringGoalPortfolio:
    """Selects the next runnable engineering goal from a portfolio."""

    def decide_next_goal(
        self,
        goals: Sequence[EngineeringGoalRecord | Mapping[str, Any]],
    ) -> dict[str, Any]:
        records = [_record(goal) for goal in goals]
        runnable: list[EngineeringGoalRecord] = []
        skipped: list[dict[str, Any]] = []

        for record in records:
            status = record.status.lower()
            if status in TERMINAL_NON_RUNNABLE_STATUSES:
                skipped.append(
                    {
                        "goal_id": record.goal_id,
                        "status": status,
                        "reason": f"goal_status_{status}",
                    }
                )
                continue
            runnable.append(record)

        if not runnable:
            return {
                "schema": PORTFOLIO_DECISION_SCHEMA,
                "selected_goal_id": "",
                "decision": "no_runnable_goal",
                "reason": "no_runnable_goals_available",
                "skipped_goals": skipped,
            }

        selected = sorted(
            runnable,
            key=lambda item: (-item.priority, item.created_at, item.goal_id),
        )[0]
        for record in records:
            if record.goal_id == selected.goal_id:
                continue
            if record in runnable:
                skipped.append(
                    {
                        "goal_id": record.goal_id,
                        "status": record.status,
                        "reason": "lower_priority_or_tie_break",
                    }
                )

        return {
            "schema": PORTFOLIO_DECISION_SCHEMA,
            "selected_goal_id": selected.goal_id,
            "decision": "select_goal",
            "reason": "highest_priority_runnable_goal",
            "skipped_goals": skipped,
        }

    def selected_goal(
        self,
        goals: Sequence[EngineeringGoalRecord | Mapping[str, Any]],
    ) -> EngineeringGoalRecord | None:
        records = [_record(goal) for goal in goals]
        decision = self.decide_next_goal(records)
        selected_goal_id = _clean_text(decision.get("selected_goal_id"))
        if not selected_goal_id:
            return None
        for record in records:
            if record.goal_id == selected_goal_id:
                return record
        return None

    def route_selected_goal(
        self,
        goals: Sequence[EngineeringGoalRecord | Mapping[str, Any]],
        *,
        planning_loop: Any,
    ) -> dict[str, Any]:
        records = [_record(goal) for goal in goals]
        decision = self.decide_next_goal(records)
        selected_goal_id = _clean_text(decision.get("selected_goal_id"))
        if not selected_goal_id:
            return {
                "schema": ENGINEERING_GOAL_PORTFOLIO_SCHEMA,
                "ok": False,
                "mode": "engineering_goal_portfolio",
                "portfolio_decision": decision,
                "planning_result": {},
                "execution_path": {
                    "portfolio_selects_only": True,
                    "direct_execution": False,
                    "existing_planning_loop_reused": False,
                    "new_execution_path": False,
                },
            }

        selected = next(record for record in records if record.goal_id == selected_goal_id)
        planning_result = planning_loop.run(selected.as_payload())
        return {
            "schema": ENGINEERING_GOAL_PORTFOLIO_SCHEMA,
            "ok": bool(_as_mapping(planning_result).get("ok")),
            "mode": "engineering_goal_portfolio",
            "portfolio_decision": decision,
            "planning_result": copy.deepcopy(dict(planning_result)) if isinstance(planning_result, Mapping) else {},
            "execution_path": {
                "portfolio_selects_only": True,
                "direct_execution": False,
                "existing_planning_loop_reused": True,
                "new_execution_path": False,
            },
        }


__all__ = [
    "ENGINEERING_GOAL_PORTFOLIO_SCHEMA",
    "PORTFOLIO_DECISION_SCHEMA",
    "EngineeringGoalPortfolio",
    "EngineeringGoalRecord",
]
