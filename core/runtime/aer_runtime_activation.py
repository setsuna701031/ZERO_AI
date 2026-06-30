from __future__ import annotations

import copy
from typing import Any, Dict

from core.runtime.aer_runtime_session import (
    runtime_session_to_summary as _runtime_session_to_summary,
    validate_runtime_session as _validate_runtime_session,
)

__all__ = [
    "create_runtime_activation",
    "validate_runtime_activation",
    "runtime_activation_to_summary",
]


_CONTRACT = "aer.runtime_activation.v2"
_OUTCOMES = ("continue", "approval_required", "issue_reported", "stopped")
_ACTIVATION_FIELDS = frozenset(("outcome", "runtime_session", "session_valid"))
_RUNTIME_ACTIVATION_FIELDS = frozenset(("contract", "outcome", "runtime_activation", "valid", "errors"))
_FIELD_PURPOSES = {
    "contract": "schema identifier",
    "outcome": "runtime-visible session result",
    "runtime_activation": "minimal runtime activation intent summary",
    "valid": "structural validity of this activation contract",
    "errors": "structural validation errors",
}
_ACTIVATION_FIELD_PURPOSES = {
    "outcome": "runtime-visible session result",
    "runtime_session": "minimal runtime session intent summary",
    "session_valid": "structural validity of the source session contract",
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


def _project_session(runtime_session: Any) -> Dict[str, Any]:
    summary = _runtime_session_to_summary(
        runtime_session if isinstance(runtime_session, dict) else {}
    )
    return _sanitize_session(summary.get("runtime_session"))


def _build_runtime_activation(*, outcome: Any, runtime_session: Any, session_valid: bool) -> Dict[str, Any]:
    return {
        "outcome": outcome,
        "runtime_session": _sanitize_session(runtime_session),
        "session_valid": session_valid,
    }


def create_runtime_activation(*, runtime_session: Any) -> Dict[str, Any]:
    validation = _validate_runtime_session(runtime_session)
    source_valid = validation["valid"]
    source_summary = _runtime_session_to_summary(
        runtime_session if isinstance(runtime_session, dict) else {}
    )
    outcome = source_summary.get("outcome") if source_valid else "issue_reported"

    return {
        "contract": _CONTRACT,
        "outcome": outcome,
        "runtime_activation": _build_runtime_activation(
            outcome=outcome,
            runtime_session=_project_session(runtime_session),
            session_valid=source_valid,
        ),
        "valid": source_valid,
        "errors": copy.deepcopy(validation["errors"]),
    }


def validate_runtime_activation(payload: Any) -> Dict[str, Any]:
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
    if "runtime_activation" not in payload:
        errors.append("missing required field: runtime_activation")
    if "valid" not in payload:
        errors.append("missing required field: valid")
    if "errors" not in payload:
        errors.append("missing required field: errors")

    if set(payload) != _RUNTIME_ACTIVATION_FIELDS:
        errors.append("runtime activation fields must match declared contract")

    if payload.get("contract") != _CONTRACT:
        errors.append("invalid contract")

    if payload.get("outcome") not in _OUTCOMES:
        errors.append(f"invalid outcome: {payload.get('outcome')}")

    runtime_activation = payload.get("runtime_activation")
    if not isinstance(runtime_activation, dict):
        errors.append("runtime_activation must be a dict")
    else:
        if set(runtime_activation) != _ACTIVATION_FIELDS:
            errors.append("runtime_activation fields must match declared contract")

        if runtime_activation.get("outcome") not in _OUTCOMES:
            errors.append(f"invalid runtime_activation outcome: {runtime_activation.get('outcome')}")
        elif runtime_activation.get("outcome") != payload.get("outcome"):
            errors.append("outcome must match runtime_activation outcome")

        session = runtime_activation.get("runtime_session")
        if not isinstance(session, dict):
            errors.append("runtime_activation runtime_session must be a dict")
        else:
            normalized = _sanitize_session(session)
            if session != normalized:
                errors.append("runtime_activation runtime_session must match runtime activation summary")

        if not isinstance(runtime_activation.get("session_valid"), bool):
            errors.append("runtime_activation session_valid must be a bool")
        elif isinstance(payload.get("valid"), bool) and runtime_activation.get("session_valid") != payload.get("valid"):
            errors.append("runtime_activation session_valid must match valid")

    if not isinstance(payload.get("valid"), bool):
        errors.append("valid must be a bool")

    if not isinstance(payload.get("errors"), list):
        errors.append("errors must be a list")
    elif payload.get("valid") is True:
        if payload.get("errors"):
            errors.append("valid runtime activation must not include errors")
    elif payload.get("valid") is False:
        if payload.get("outcome") != "issue_reported":
            errors.append("invalid runtime activation must report issue")
        if not payload.get("errors"):
            errors.append("invalid runtime activation must include errors")
        errors.append("runtime activation contains invalid runtime session")

    return {
        "valid": not errors,
        "contract": _CONTRACT,
        "errors": errors,
    }


def runtime_activation_to_summary(runtime_activation: dict) -> Dict[str, Any]:
    activation = runtime_activation.get("runtime_activation") if isinstance(runtime_activation, dict) else {}
    if not isinstance(activation, dict):
        activation = {}

    return {
        "outcome": runtime_activation.get("outcome") if isinstance(runtime_activation, dict) else None,
        "runtime_activation": _build_runtime_activation(
            outcome=activation.get("outcome"),
            runtime_session=activation.get("runtime_session") or {},
            session_valid=activation.get("session_valid") is True,
        ),
        "valid": runtime_activation.get("valid") if isinstance(runtime_activation, dict) else None,
    }
