from __future__ import annotations

from typing import Any, Dict

from core.runtime.aer_operator_approval import validate_approval as _validate_approval
from core.runtime.aer_operator_decision import validate_decision as _validate_decision
from core.runtime.aer_operator_issue_reporter import validate_issue as _validate_issue
from core.runtime.aer_operator_stop_condition import (
    validate_stop_condition as _validate_stop_condition,
)

__all__ = ["evaluate_decision", "decision_flow_summary"]


def evaluate_decision(decision: Any) -> Dict[str, Any]:
    validation = _validate_decision(decision)

    if not validation["ok"]:
        outcome = "issue_reported"
    elif decision.get("decision_type") == "continue":
        outcome = "continue"
    elif decision.get("decision_type") == "request_approval":
        outcome = "approval_required"
    elif decision.get("decision_type") == "report_issue":
        outcome = "issue_reported"
    elif decision.get("decision_type") == "stop":
        outcome = "stopped"
    else:
        outcome = "issue_reported"

    return {
        "outcome": outcome,
        "decision_id": decision.get("decision_id") if isinstance(decision, dict) else None,
        "decision_type": decision.get("decision_type") if isinstance(decision, dict) else None,
        "status": decision.get("status") if isinstance(decision, dict) else None,
    }


def decision_flow_summary(flow: dict) -> Dict[str, Any]:
    return {
        "outcome": flow.get("outcome"),
        "decision_id": flow.get("decision_id"),
        "decision_type": flow.get("decision_type"),
        "status": flow.get("status"),
    }
