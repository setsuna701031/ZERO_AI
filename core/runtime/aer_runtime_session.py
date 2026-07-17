from __future__ import annotations

import copy
from typing import Any, Dict

from core.runtime.aer_runtime_projection import (
    runtime_projection_to_summary as _runtime_projection_to_summary,
    validate_runtime_projection as _validate_runtime_projection,
)

__all__ = [
    "create_runtime_session",
    "validate_runtime_session",
    "runtime_session_to_summary",
]


_CONTRACT = "aer.runtime_session.v2"
_OUTCOMES = ("continue", "approval_required", "issue_reported", "stopped")
_SESSION_FIELDS = frozenset(("outcome", "operator_handoff", "projection_valid"))
_RUNTIME_SESSION_FIELDS = frozenset(("contract", "outcome", "runtime_session", "valid", "errors"))
_FIELD_PURPOSES = {
    "contract": "schema identifier",
    "outcome": "runtime-visible projection result",
    "runtime_session": "minimal runtime session intent summary",
    "valid": "structural validity of this session contract",
    "errors": "structural validation errors",
}
_SESSION_FIELD_PURPOSES = {
    "outcome": "runtime-visible projection result",
    "operator_handoff": "minimal upstream operator intent summary",
    "projection_valid": "structural validity of the source projection",
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


def _project_operator_handoff(runtime_projection: Any) -> Dict[str, Any]:
    summary = _runtime_projection_to_summary(
        runtime_projection if isinstance(runtime_projection, dict) else {}
    )
    return _sanitize_operator_handoff(summary.get("operator_handoff"))


def _build_runtime_session(*, outcome: Any, operator_handoff: Any, projection_valid: bool) -> Dict[str, Any]:
    return {
        "outcome": outcome,
        "operator_handoff": _sanitize_operator_handoff(operator_handoff),
        "projection_valid": projection_valid,
    }


def create_runtime_session(*, runtime_projection: Any) -> Dict[str, Any]:
    validation = _validate_runtime_projection(runtime_projection)
    source_valid = validation["valid"]
    source_summary = _runtime_projection_to_summary(
        runtime_projection if isinstance(runtime_projection, dict) else {}
    )
    outcome = source_summary.get("outcome") if source_valid else "issue_reported"

    return {
        "contract": _CONTRACT,
        "outcome": outcome,
        "runtime_session": _build_runtime_session(
            outcome=outcome,
            operator_handoff=_project_operator_handoff(runtime_projection),
            projection_valid=source_valid,
        ),
        "valid": source_valid,
        "errors": copy.deepcopy(validation["errors"]),
    }


def validate_runtime_session(payload: Any) -> Dict[str, Any]:
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
    if "runtime_session" not in payload:
        errors.append("missing required field: runtime_session")
    if "valid" not in payload:
        errors.append("missing required field: valid")
    if "errors" not in payload:
        errors.append("missing required field: errors")

    if set(payload) != _RUNTIME_SESSION_FIELDS:
        errors.append("runtime session fields must match declared contract")

    if payload.get("contract") != _CONTRACT:
        errors.append("invalid contract")

    if payload.get("outcome") not in _OUTCOMES:
        errors.append(f"invalid outcome: {payload.get('outcome')}")

    runtime_session = payload.get("runtime_session")
    if not isinstance(runtime_session, dict):
        errors.append("runtime_session must be a dict")
    else:
        if set(runtime_session) != _SESSION_FIELDS:
            errors.append("runtime_session fields must match declared contract")

        if runtime_session.get("outcome") not in _OUTCOMES:
            errors.append(f"invalid runtime_session outcome: {runtime_session.get('outcome')}")
        elif runtime_session.get("outcome") != payload.get("outcome"):
            errors.append("outcome must match runtime_session outcome")

        operator_handoff = runtime_session.get("operator_handoff")
        if not isinstance(operator_handoff, dict):
            errors.append("runtime_session operator_handoff must be a dict")
        else:
            normalized = _sanitize_operator_handoff(operator_handoff)
            if operator_handoff != normalized:
                errors.append("runtime_session operator_handoff must match runtime session summary")

        if not isinstance(runtime_session.get("projection_valid"), bool):
            errors.append("runtime_session projection_valid must be a bool")
        elif isinstance(payload.get("valid"), bool) and runtime_session.get("projection_valid") != payload.get("valid"):
            errors.append("runtime_session projection_valid must match valid")

    if not isinstance(payload.get("valid"), bool):
        errors.append("valid must be a bool")

    if not isinstance(payload.get("errors"), list):
        errors.append("errors must be a list")
    elif payload.get("valid") is True:
        if payload.get("errors"):
            errors.append("valid runtime session must not include errors")
    elif payload.get("valid") is False:
        if payload.get("outcome") != "issue_reported":
            errors.append("invalid runtime session must report issue")
        if not payload.get("errors"):
            errors.append("invalid runtime session must include errors")
        errors.append("runtime session contains invalid runtime projection")

    return {
        "valid": not errors,
        "contract": _CONTRACT,
        "errors": errors,
    }


def runtime_session_to_summary(runtime_session: dict) -> Dict[str, Any]:
    session = runtime_session.get("runtime_session") if isinstance(runtime_session, dict) else {}
    if not isinstance(session, dict):
        session = {}

    return {
        "outcome": runtime_session.get("outcome") if isinstance(runtime_session, dict) else None,
        "runtime_session": _build_runtime_session(
            outcome=session.get("outcome"),
            operator_handoff=session.get("operator_handoff") or {},
            projection_valid=session.get("projection_valid") is True,
        ),
        "valid": runtime_session.get("valid") if isinstance(runtime_session, dict) else None,
    }
