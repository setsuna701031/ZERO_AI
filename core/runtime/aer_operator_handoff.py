from __future__ import annotations

import copy
from typing import Any, Dict

from core.runtime.aer_operator_state import (
    operator_state_to_summary as _operator_state_to_summary,
    validate_operator_state as _validate_operator_state,
)

__all__ = [
    "create_operator_handoff",
    "validate_operator_handoff",
    "operator_handoff_to_summary",
]


_CONTRACT = "aer.operator_handoff.v2"
_OUTCOMES = ("continue", "approval_required", "issue_reported", "stopped")
_HANDOFF_FIELDS = frozenset(("contract", "outcome", "operator_state", "state_valid", "errors"))


def create_operator_handoff(*, operator_state: Any) -> Dict[str, Any]:
    validation = _validate_operator_state(operator_state)
    source = operator_state if isinstance(operator_state, dict) else {}
    state_summary = _operator_state_to_summary(source)
    state_valid = validation["ok"]
    outcome = state_summary.get("outcome") if state_valid else "issue_reported"

    return {
        "contract": _CONTRACT,
        "outcome": outcome,
        "operator_state": copy.deepcopy(state_summary),
        "state_valid": state_valid,
        "errors": copy.deepcopy(validation["errors"]),
    }


def validate_operator_handoff(payload: Any) -> Dict[str, Any]:
    errors = []

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "contract": _CONTRACT,
            "errors": ["payload must be a dict"],
        }

    if "contract" not in payload:
        errors.append("missing required field: contract")
    if "outcome" not in payload:
        errors.append("missing required field: outcome")
    if "operator_state" not in payload:
        errors.append("missing required field: operator_state")
    if "state_valid" not in payload:
        errors.append("missing required field: state_valid")
    if "errors" not in payload:
        errors.append("missing required field: errors")

    if set(payload) != _HANDOFF_FIELDS:
        errors.append("handoff fields must match declared contract")

    if payload.get("contract") != _CONTRACT:
        errors.append("invalid contract")

    if payload.get("outcome") not in _OUTCOMES:
        errors.append(f"invalid outcome: {payload.get('outcome')}")

    state_summary = payload.get("operator_state")
    if not isinstance(state_summary, dict):
        errors.append("operator_state must be a dict")
    else:
        normalized = _operator_state_to_summary(state_summary)
        if state_summary != normalized:
            errors.append("operator_state must match operator state summary")
        if payload.get("state_valid") is True and state_summary.get("outcome") != payload.get("outcome"):
            errors.append("outcome must match operator_state outcome")

    if not isinstance(payload.get("state_valid"), bool):
        errors.append("state_valid must be a bool")

    if not isinstance(payload.get("errors"), list):
        errors.append("errors must be a list")
    elif payload.get("state_valid") is True and payload.get("errors"):
        errors.append("valid handoff must not include errors")
    elif payload.get("state_valid") is False:
        if payload.get("outcome") != "issue_reported":
            errors.append("invalid state handoff must report issue")
        if not payload.get("errors"):
            errors.append("invalid state handoff must include errors")

    return {
        "ok": not errors,
        "contract": _CONTRACT,
        "errors": errors,
    }


def operator_handoff_to_summary(handoff: dict) -> Dict[str, Any]:
    return {
        "outcome": handoff.get("outcome"),
        "operator_state": _operator_state_to_summary(handoff.get("operator_state") or {}),
        "state_valid": handoff.get("state_valid"),
    }
