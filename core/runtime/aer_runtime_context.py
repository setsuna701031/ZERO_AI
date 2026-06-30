from __future__ import annotations

import copy
from typing import Any, Dict

from core.runtime.aer_runtime_bootstrap import (
    runtime_bootstrap_to_summary as _runtime_bootstrap_to_summary,
    validate_runtime_bootstrap as _validate_runtime_bootstrap,
)

__all__ = [
    "create_runtime_context",
    "validate_runtime_context",
    "runtime_context_to_summary",
]


_CONTRACT = "aer.runtime_context.v2"
_OUTCOMES = ("continue", "approval_required", "issue_reported", "stopped")
_CONTEXT_FIELDS = frozenset(("contract", "outcome", "operator_handoff", "valid", "errors"))
_FIELD_PURPOSES = {
    "contract": "schema identifier",
    "outcome": "runtime-visible upstream result",
    "operator_handoff": "minimal upstream operator intent summary",
    "valid": "structural validity of this context",
    "errors": "structural validation errors",
}


def _project_operator_handoff(runtime_bootstrap: Any) -> Dict[str, Any]:
    bootstrap_summary = _runtime_bootstrap_to_summary(
        runtime_bootstrap if isinstance(runtime_bootstrap, dict) else {}
    )
    runtime_intake = bootstrap_summary.get("runtime_intake") or {}
    operator_handoff = runtime_intake.get("operator_handoff") or {}
    return copy.deepcopy(operator_handoff)


def create_runtime_context(*, runtime_bootstrap: Any) -> Dict[str, Any]:
    validation = _validate_runtime_bootstrap(runtime_bootstrap)
    source = runtime_bootstrap if isinstance(runtime_bootstrap, dict) else {}
    source_valid = validation["valid"]
    outcome = source.get("outcome") if source_valid else "issue_reported"

    return {
        "contract": _CONTRACT,
        "outcome": outcome,
        "operator_handoff": _project_operator_handoff(source),
        "valid": source_valid,
        "errors": copy.deepcopy(validation["errors"]),
    }


def validate_runtime_context(payload: Any) -> Dict[str, Any]:
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

    if set(payload) != _CONTEXT_FIELDS:
        errors.append("context fields must match declared contract")

    if payload.get("contract") != _CONTRACT:
        errors.append("invalid contract")

    if payload.get("outcome") not in _OUTCOMES:
        errors.append(f"invalid outcome: {payload.get('outcome')}")

    operator_handoff = payload.get("operator_handoff")
    if not isinstance(operator_handoff, dict):
        errors.append("operator_handoff must be a dict")
    else:
        normalized = _project_operator_handoff({"runtime_intake": {"operator_handoff": operator_handoff}})
        if operator_handoff != normalized:
            errors.append("operator_handoff must match runtime context summary")

    if not isinstance(payload.get("valid"), bool):
        errors.append("valid must be a bool")

    if not isinstance(payload.get("errors"), list):
        errors.append("errors must be a list")
    elif payload.get("valid") is True:
        if payload.get("errors"):
            errors.append("valid runtime context must not include errors")
        elif isinstance(operator_handoff, dict) and operator_handoff.get("outcome") != payload.get("outcome"):
            errors.append("outcome must match operator_handoff outcome")
    elif payload.get("valid") is False:
        if payload.get("outcome") != "issue_reported":
            errors.append("invalid runtime context must report issue")
        if not payload.get("errors"):
            errors.append("invalid runtime context must include errors")
        errors.append("runtime context contains invalid runtime bootstrap")

    return {
        "valid": not errors,
        "contract": _CONTRACT,
        "errors": errors,
    }


def runtime_context_to_summary(context: dict) -> Dict[str, Any]:
    return {
        "outcome": context.get("outcome"),
        "operator_handoff": _project_operator_handoff(
            {"runtime_intake": {"operator_handoff": context.get("operator_handoff") or {}}}
        ),
        "valid": context.get("valid"),
    }
