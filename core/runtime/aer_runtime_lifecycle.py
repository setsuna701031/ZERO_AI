from __future__ import annotations

import copy
from typing import Any, Dict

from core.runtime.aer_runtime_activation import (
    runtime_activation_to_summary as _runtime_activation_to_summary,
    validate_runtime_activation as _validate_runtime_activation,
)

__all__ = [
    "create_runtime_lifecycle",
    "validate_runtime_lifecycle",
    "runtime_lifecycle_to_summary",
]


_CONTRACT = "aer.runtime_lifecycle.v2"
_OUTCOMES = ("continue", "approval_required", "issue_reported", "stopped")
_LIFECYCLE_FIELDS = frozenset(("outcome", "runtime_activation", "activation_valid"))
_RUNTIME_LIFECYCLE_FIELDS = frozenset(("contract", "outcome", "runtime_lifecycle", "valid", "errors"))
_FIELD_PURPOSES = {
    "contract": "schema identifier",
    "outcome": "runtime-visible activation result",
    "runtime_lifecycle": "minimal runtime lifecycle intent summary",
    "valid": "structural validity of this lifecycle contract",
    "errors": "structural validation errors",
}
_LIFECYCLE_FIELD_PURPOSES = {
    "outcome": "runtime-visible activation result",
    "runtime_activation": "minimal runtime activation intent summary",
    "activation_valid": "structural validity of the source activation contract",
}


def _copy_dict(value: Any) -> Dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _sanitize_decision_summary(value: Any) -> Dict[str, Any]:
    source = _copy_dict(value)
    return {
        "outcome": source.get("outcome"),
        "decision_id": source.get("decision_id"),
        "decision_type": source.get("decision_type"),
        "status": source.get("status"),
    }


def _sanitize_plan_summary(value: Any) -> Dict[str, Any]:
    source = _copy_dict(value)
    return {
        "outcome": source.get("outcome"),
        "plan_id": source.get("plan_id"),
        "plan_type": source.get("plan_type"),
        "status": source.get("status"),
    }


def _sanitize_composition_summary(value: Any) -> Dict[str, Any]:
    source = _copy_dict(value)
    return {
        "outcome": source.get("outcome"),
        "decision": _sanitize_decision_summary(source.get("decision")),
        "plan": _sanitize_plan_summary(source.get("plan")),
    }


def _sanitize_operator_state(value: Any) -> Dict[str, Any]:
    source = _copy_dict(value)
    return {
        "outcome": source.get("outcome"),
        "composition_summary": _sanitize_composition_summary(source.get("composition_summary")),
    }


def _sanitize_operator_handoff(value: Any) -> Dict[str, Any]:
    source = _copy_dict(value)
    return {
        "outcome": source.get("outcome"),
        "operator_state": _sanitize_operator_state(source.get("operator_state")),
        "state_valid": source.get("state_valid") is True,
    }


def _sanitize_session(value: Any) -> Dict[str, Any]:
    source = _copy_dict(value)
    return {
        "outcome": source.get("outcome"),
        "operator_handoff": _sanitize_operator_handoff(source.get("operator_handoff")),
        "projection_valid": source.get("projection_valid") is True,
    }


def _sanitize_activation(value: Any) -> Dict[str, Any]:
    source = _copy_dict(value)
    return {
        "outcome": source.get("outcome"),
        "runtime_session": _sanitize_session(source.get("runtime_session")),
        "session_valid": source.get("session_valid") is True,
    }


def _project_activation(runtime_activation: Any) -> Dict[str, Any]:
    summary = _runtime_activation_to_summary(
        runtime_activation if isinstance(runtime_activation, dict) else {}
    )
    return _sanitize_activation(summary.get("runtime_activation"))


def _build_runtime_lifecycle(*, outcome: Any, runtime_activation: Any, activation_valid: bool) -> Dict[str, Any]:
    return {
        "outcome": outcome,
        "runtime_activation": _sanitize_activation(runtime_activation),
        "activation_valid": activation_valid,
    }


def create_runtime_lifecycle(*, runtime_activation: Any) -> Dict[str, Any]:
    validation = _validate_runtime_activation(runtime_activation)
    source_valid = validation["valid"]
    source_summary = _runtime_activation_to_summary(
        runtime_activation if isinstance(runtime_activation, dict) else {}
    )
    outcome = source_summary.get("outcome") if source_valid else "issue_reported"

    return {
        "contract": _CONTRACT,
        "outcome": outcome,
        "runtime_lifecycle": _build_runtime_lifecycle(
            outcome=outcome,
            runtime_activation=_project_activation(runtime_activation),
            activation_valid=source_valid,
        ),
        "valid": source_valid,
        "errors": copy.deepcopy(validation["errors"]),
    }


def validate_runtime_lifecycle(payload: Any) -> Dict[str, Any]:
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
    if "runtime_lifecycle" not in payload:
        errors.append("missing required field: runtime_lifecycle")
    if "valid" not in payload:
        errors.append("missing required field: valid")
    if "errors" not in payload:
        errors.append("missing required field: errors")

    if set(payload) != _RUNTIME_LIFECYCLE_FIELDS:
        errors.append("runtime lifecycle fields must match declared contract")

    if payload.get("contract") != _CONTRACT:
        errors.append("invalid contract")

    if payload.get("outcome") not in _OUTCOMES:
        errors.append(f"invalid outcome: {payload.get('outcome')}")

    runtime_lifecycle = payload.get("runtime_lifecycle")
    if not isinstance(runtime_lifecycle, dict):
        errors.append("runtime_lifecycle must be a dict")
    else:
        if set(runtime_lifecycle) != _LIFECYCLE_FIELDS:
            errors.append("runtime_lifecycle fields must match declared contract")

        if runtime_lifecycle.get("outcome") not in _OUTCOMES:
            errors.append(f"invalid runtime_lifecycle outcome: {runtime_lifecycle.get('outcome')}")
        elif runtime_lifecycle.get("outcome") != payload.get("outcome"):
            errors.append("outcome must match runtime_lifecycle outcome")

        activation = runtime_lifecycle.get("runtime_activation")
        if not isinstance(activation, dict):
            errors.append("runtime_lifecycle runtime_activation must be a dict")
        else:
            normalized = _sanitize_activation(activation)
            if activation != normalized:
                errors.append("runtime_lifecycle runtime_activation must match runtime lifecycle summary")

        if not isinstance(runtime_lifecycle.get("activation_valid"), bool):
            errors.append("runtime_lifecycle activation_valid must be a bool")
        elif isinstance(payload.get("valid"), bool) and runtime_lifecycle.get("activation_valid") != payload.get("valid"):
            errors.append("runtime_lifecycle activation_valid must match valid")

    if not isinstance(payload.get("valid"), bool):
        errors.append("valid must be a bool")

    if not isinstance(payload.get("errors"), list):
        errors.append("errors must be a list")
    elif payload.get("valid") is True:
        if payload.get("errors"):
            errors.append("valid runtime lifecycle must not include errors")
    elif payload.get("valid") is False:
        if payload.get("outcome") != "issue_reported":
            errors.append("invalid runtime lifecycle must report issue")
        if not payload.get("errors"):
            errors.append("invalid runtime lifecycle must include errors")
        errors.append("runtime lifecycle contains invalid runtime activation")

    return {
        "valid": not errors,
        "contract": _CONTRACT,
        "errors": errors,
    }


def runtime_lifecycle_to_summary(runtime_lifecycle: dict) -> Dict[str, Any]:
    lifecycle = runtime_lifecycle.get("runtime_lifecycle") if isinstance(runtime_lifecycle, dict) else {}
    if not isinstance(lifecycle, dict):
        lifecycle = {}

    return {
        "outcome": runtime_lifecycle.get("outcome") if isinstance(runtime_lifecycle, dict) else None,
        "runtime_lifecycle": _build_runtime_lifecycle(
            outcome=lifecycle.get("outcome"),
            runtime_activation=lifecycle.get("runtime_activation") or {},
            activation_valid=lifecycle.get("activation_valid") is True,
        ),
        "valid": runtime_lifecycle.get("valid") if isinstance(runtime_lifecycle, dict) else None,
    }
