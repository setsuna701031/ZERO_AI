from __future__ import annotations

import copy
from typing import Any, Dict

from core.runtime.aer_operator_handoff import (
    operator_handoff_to_summary as _operator_handoff_to_summary,
    validate_operator_handoff as _validate_operator_handoff,
)

__all__ = [
    "create_runtime_intake",
    "validate_runtime_intake",
    "runtime_intake_to_summary",
]


_CONTRACT = "aer.runtime_intake.v2"
_OUTCOMES = ("continue", "approval_required", "issue_reported", "stopped")
_INTAKE_FIELDS = frozenset(("contract", "outcome", "operator_handoff", "valid", "errors"))


def create_runtime_intake(*, operator_handoff: Any) -> Dict[str, Any]:
    validation = _validate_operator_handoff(operator_handoff)
    source = operator_handoff if isinstance(operator_handoff, dict) else {}
    handoff_summary = _operator_handoff_to_summary(source)
    source_valid = validation["ok"]
    outcome = handoff_summary.get("outcome") if source_valid else "issue_reported"

    return {
        "contract": _CONTRACT,
        "outcome": outcome,
        "operator_handoff": copy.deepcopy(handoff_summary),
        "valid": source_valid,
        "errors": copy.deepcopy(validation["errors"]),
    }


def validate_runtime_intake(payload: Any) -> Dict[str, Any]:
    errors = []

    if not isinstance(payload, dict):
        return {
            "valid": False,
            "contract": _CONTRACT,
            "errors": ["payload must be a dict"],
        }

    if "contract" not in payload:
        errors.append("missing required field: contract")
    if "outcome" not in payload:
        errors.append("missing required field: outcome")
    if "operator_handoff" not in payload:
        errors.append("missing required field: operator_handoff")
    if "valid" not in payload:
        errors.append("missing required field: valid")
    if "errors" not in payload:
        errors.append("missing required field: errors")

    if set(payload) != _INTAKE_FIELDS:
        errors.append("intake fields must match declared contract")

    if payload.get("contract") != _CONTRACT:
        errors.append("invalid contract")

    if payload.get("outcome") not in _OUTCOMES:
        errors.append(f"invalid outcome: {payload.get('outcome')}")

    handoff_summary = payload.get("operator_handoff")
    if not isinstance(handoff_summary, dict):
        errors.append("operator_handoff must be a dict")
    else:
        normalized = _operator_handoff_to_summary(handoff_summary)
        if handoff_summary != normalized:
            errors.append("operator_handoff must match operator handoff summary")

    if not isinstance(payload.get("valid"), bool):
        errors.append("valid must be a bool")

    if not isinstance(payload.get("errors"), list):
        errors.append("errors must be a list")
    elif payload.get("valid") is True:
        if payload.get("errors"):
            errors.append("valid runtime intake must not include errors")
        elif isinstance(handoff_summary, dict) and handoff_summary.get("outcome") != payload.get("outcome"):
            errors.append("outcome must match operator_handoff outcome")
    elif payload.get("valid") is False:
        if payload.get("outcome") != "issue_reported":
            errors.append("invalid runtime intake must report issue")
        if not payload.get("errors"):
            errors.append("invalid runtime intake must include errors")
        errors.append("runtime intake contains invalid operator handoff")

    return {
        "valid": not errors,
        "contract": _CONTRACT,
        "errors": errors,
    }


def runtime_intake_to_summary(intake: dict) -> Dict[str, Any]:
    return {
        "outcome": intake.get("outcome"),
        "operator_handoff": _operator_handoff_to_summary(intake.get("operator_handoff") or {}),
        "valid": intake.get("valid"),
    }
