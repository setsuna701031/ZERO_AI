from __future__ import annotations

from typing import Any, Dict

from core.runtime.aer_operator_plan import validate_plan as _validate_plan

__all__ = ["evaluate_plan", "plan_flow_summary"]


def evaluate_plan(plan: Any) -> Dict[str, Any]:
    validation = _validate_plan(plan)

    if not validation["ok"]:
        outcome = "issue_reported"
    elif plan.get("plan_type") == "continue":
        outcome = "continue"
    elif plan.get("plan_type") == "request_approval":
        outcome = "approval_required"
    elif plan.get("plan_type") == "report_issue":
        outcome = "issue_reported"
    elif plan.get("plan_type") == "stop":
        outcome = "stopped"
    else:
        outcome = "issue_reported"

    return {
        "outcome": outcome,
        "plan_id": plan.get("plan_id") if isinstance(plan, dict) else None,
        "plan_type": plan.get("plan_type") if isinstance(plan, dict) else None,
        "status": plan.get("status") if isinstance(plan, dict) else None,
    }


def plan_flow_summary(flow: dict) -> Dict[str, Any]:
    return {
        "outcome": flow.get("outcome"),
        "plan_id": flow.get("plan_id"),
        "plan_type": flow.get("plan_type"),
        "status": flow.get("status"),
    }
