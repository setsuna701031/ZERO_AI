from __future__ import annotations

import copy
from typing import Any, Dict

from core.runtime.aer_runtime_context import (
    runtime_context_to_summary as _runtime_context_to_summary,
    validate_runtime_context as _validate_runtime_context,
)

__all__ = [
    "create_runtime_projection",
    "validate_runtime_projection",
    "runtime_projection_to_summary",
]


_CONTRACT = "aer.runtime_projection.v2"
_OUTCOMES = ("continue", "approval_required", "issue_reported", "stopped")
_PROJECTION_FIELDS = frozenset(("contract", "outcome", "operator_handoff", "valid", "errors"))
_FIELD_PURPOSES = {
    "contract": "schema identifier",
    "outcome": "runtime-visible context result",
    "operator_handoff": "minimal upstream operator intent summary",
    "valid": "structural validity of this projection",
    "errors": "structural validation errors",
}


def _project_operator_handoff(runtime_context: Any) -> Dict[str, Any]:
    summary = _runtime_context_to_summary(runtime_context if isinstance(runtime_context, dict) else {})
    operator_handoff = summary.get("operator_handoff") or {}
    return copy.deepcopy(operator_handoff)


def create_runtime_projection(*, runtime_context: Any) -> Dict[str, Any]:
    validation = _validate_runtime_context(runtime_context)
    source_valid = validation["valid"]
    source_summary = _runtime_context_to_summary(runtime_context if isinstance(runtime_context, dict) else {})
    outcome = source_summary.get("outcome") if source_valid else "issue_reported"

    return {
        "contract": _CONTRACT,
        "outcome": outcome,
        "operator_handoff": _project_operator_handoff(runtime_context),
        "valid": source_valid,
        "errors": copy.deepcopy(validation["errors"]),
    }


def validate_runtime_projection(payload: Any) -> Dict[str, Any]:
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

    if set(payload) != _PROJECTION_FIELDS:
        errors.append("projection fields must match declared contract")

    if payload.get("contract") != _CONTRACT:
        errors.append("invalid contract")

    if payload.get("outcome") not in _OUTCOMES:
        errors.append(f"invalid outcome: {payload.get('outcome')}")

    operator_handoff = payload.get("operator_handoff")
    if not isinstance(operator_handoff, dict):
        errors.append("operator_handoff must be a dict")
    else:
        normalized = _project_operator_handoff(
            {
                "contract": "aer.runtime_context.v2",
                "outcome": payload.get("outcome"),
                "operator_handoff": operator_handoff,
                "valid": True,
                "errors": [],
            }
        )
        if operator_handoff != normalized:
            errors.append("operator_handoff must match runtime projection summary")

    if not isinstance(payload.get("valid"), bool):
        errors.append("valid must be a bool")

    if not isinstance(payload.get("errors"), list):
        errors.append("errors must be a list")
    elif payload.get("valid") is True:
        if payload.get("errors"):
            errors.append("valid runtime projection must not include errors")
        elif isinstance(operator_handoff, dict) and operator_handoff.get("outcome") != payload.get("outcome"):
            errors.append("outcome must match operator_handoff outcome")
    elif payload.get("valid") is False:
        if payload.get("outcome") != "issue_reported":
            errors.append("invalid runtime projection must report issue")
        if not payload.get("errors"):
            errors.append("invalid runtime projection must include errors")
        errors.append("runtime projection contains invalid runtime context")

    return {
        "valid": not errors,
        "contract": _CONTRACT,
        "errors": errors,
    }


def runtime_projection_to_summary(projection: dict) -> Dict[str, Any]:
    return {
        "outcome": projection.get("outcome"),
        "operator_handoff": _project_operator_handoff(
            {
                "contract": "aer.runtime_context.v2",
                "outcome": projection.get("outcome"),
                "operator_handoff": projection.get("operator_handoff") or {},
                "valid": True,
                "errors": [],
            }
        ),
        "valid": projection.get("valid"),
    }
