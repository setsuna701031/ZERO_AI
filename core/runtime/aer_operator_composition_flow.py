from __future__ import annotations

from typing import Any, Dict

from core.runtime.aer_operator_decision_flow import (
    decision_flow_summary as _decision_flow_summary,
    evaluate_decision as _evaluate_decision,
)
from core.runtime.aer_operator_plan_flow import (
    evaluate_plan as _evaluate_plan,
    plan_flow_summary as _plan_flow_summary,
)

__all__ = ["compose_operator_flow", "operator_flow_to_summary"]


def compose_operator_flow(decision: Any, plan: Any) -> Dict[str, Any]:
    decision_summary = _decision_flow_summary(_evaluate_decision(decision))
    plan_summary = _plan_flow_summary(_evaluate_plan(plan))
    decision_outcome = decision_summary.get("outcome")
    plan_outcome = plan_summary.get("outcome")

    if decision_outcome == "issue_reported" or plan_outcome == "issue_reported":
        outcome = "issue_reported"
    elif decision_outcome == "stopped" or plan_outcome == "stopped":
        outcome = "stopped"
    elif decision_outcome == "approval_required" or plan_outcome == "approval_required":
        outcome = "approval_required"
    elif decision_outcome == "continue" and plan_outcome == "continue":
        outcome = "continue"
    else:
        outcome = "issue_reported"

    return {
        "outcome": outcome,
        "decision": decision_summary,
        "plan": plan_summary,
    }


def operator_flow_to_summary(flow: dict) -> Dict[str, Any]:
    return {
        "outcome": flow.get("outcome"),
        "decision": _decision_flow_summary(flow.get("decision") or {}),
        "plan": _plan_flow_summary(flow.get("plan") or {}),
    }
