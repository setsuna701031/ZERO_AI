from __future__ import annotations

from typing import Any, Dict

from core.runtime.aer_runtime_recovery_marker import (
    runtime_recovery_marker_to_summary as _runtime_recovery_marker_to_summary,
    validate_runtime_recovery_marker as _validate_runtime_recovery_marker,
)

__all__ = [
    "create_runtime_resume_marker",
    "validate_runtime_resume_marker",
    "runtime_resume_marker_to_summary",
]


_CONTRACT = "aer.runtime_resume_marker.v2"
_SUMMARY_CONTRACT = "aer.runtime.resume_marker.summary.v1"
_OUTCOMES = ("continue", "approval_required", "issue_reported", "stopped")
_MARKER_FIELDS = frozenset(("outcome", "source_outcome", "source_valid"))
_RUNTIME_RESUME_MARKER_FIELDS = frozenset(("contract", "outcome", "runtime_resume_marker", "valid", "errors"))
_FIELD_PURPOSES = {
    "contract": "schema identifier",
    "outcome": "runtime-visible resume marker result",
    "runtime_resume_marker": "minimal runtime resume marker",
    "valid": "structural validity of this resume marker contract",
    "errors": "structural validation errors",
}
_MARKER_FIELD_PURPOSES = {
    "outcome": "runtime-visible resume marker result",
    "source_outcome": "runtime-visible upstream result projected into this resume marker",
    "source_valid": "structural validity of the upstream contract",
}


def _upstream_errors(validation: Dict[str, Any]) -> list[str]:
    if validation.get("valid") is True:
        return []
    return ["invalid upstream contract"]


def _build_runtime_resume_marker(*, outcome: Any, source_outcome: Any, source_valid: bool) -> Dict[str, Any]:
    return {
        "outcome": outcome,
        "source_outcome": source_outcome,
        "source_valid": source_valid,
    }


def create_runtime_resume_marker(*, runtime_recovery_marker: Any) -> Dict[str, Any]:
    validation = _validate_runtime_recovery_marker(runtime_recovery_marker)
    source_valid = validation["valid"]
    source_summary = _runtime_recovery_marker_to_summary(
        runtime_recovery_marker if isinstance(runtime_recovery_marker, dict) else {}
    )
    source_outcome = source_summary.get("outcome")
    outcome = source_outcome if source_valid else "issue_reported"

    return {
        "contract": _CONTRACT,
        "outcome": outcome,
        "runtime_resume_marker": _build_runtime_resume_marker(
            outcome=outcome,
            source_outcome=source_outcome,
            source_valid=source_valid,
        ),
        "valid": source_valid,
        "errors": _upstream_errors(validation),
    }


def validate_runtime_resume_marker(payload: Any) -> Dict[str, Any]:
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
    if "runtime_resume_marker" not in payload:
        errors.append("missing required field: runtime_resume_marker")
    if "valid" not in payload:
        errors.append("missing required field: valid")
    if "errors" not in payload:
        errors.append("missing required field: errors")

    if set(payload) != _RUNTIME_RESUME_MARKER_FIELDS:
        errors.append("runtime resume marker fields must match declared contract")

    if payload.get("contract") != _CONTRACT:
        errors.append("invalid contract")

    if payload.get("outcome") not in _OUTCOMES:
        errors.append(f"invalid outcome: {payload.get('outcome')}")

    marker = payload.get("runtime_resume_marker")
    if not isinstance(marker, dict):
        errors.append("runtime_resume_marker must be a dict")
    else:
        if set(marker) != _MARKER_FIELDS:
            errors.append("runtime_resume_marker fields must match declared contract")

        if marker.get("outcome") not in _OUTCOMES:
            errors.append(f"invalid runtime_resume_marker outcome: {marker.get('outcome')}")
        elif marker.get("outcome") != payload.get("outcome"):
            errors.append("outcome must match runtime_resume_marker outcome")

        if marker.get("source_outcome") not in _OUTCOMES:
            errors.append(f"invalid runtime_resume_marker source_outcome: {marker.get('source_outcome')}")
        elif marker.get("source_valid") is True and marker.get("source_outcome") != payload.get("outcome"):
            errors.append("source_outcome must match outcome when source is valid")

        if not isinstance(marker.get("source_valid"), bool):
            errors.append("runtime_resume_marker source_valid must be a bool")
        elif isinstance(payload.get("valid"), bool) and marker.get("source_valid") != payload.get("valid"):
            errors.append("runtime_resume_marker source_valid must match valid")

    if not isinstance(payload.get("valid"), bool):
        errors.append("valid must be a bool")

    if not isinstance(payload.get("errors"), list):
        errors.append("errors must be a list")
    elif payload.get("valid") is True:
        if payload.get("errors"):
            errors.append("valid runtime resume marker must not include errors")
    elif payload.get("valid") is False:
        if payload.get("outcome") != "issue_reported":
            errors.append("invalid runtime resume marker must report issue")
        if not payload.get("errors"):
            errors.append("invalid runtime resume marker must include errors")
        errors.append("runtime resume marker contains invalid upstream contract")

    return {
        "valid": not errors,
        "contract": _CONTRACT,
        "errors": errors,
    }


def runtime_resume_marker_to_summary(runtime_resume_marker: dict) -> Dict[str, Any]:
    validation = validate_runtime_resume_marker(runtime_resume_marker)
    if validation["valid"] is not True:
        outcome = runtime_resume_marker.get("outcome") if isinstance(runtime_resume_marker, dict) else None
        if outcome not in _OUTCOMES:
            outcome = "continue"

        return {
            "contract": _SUMMARY_CONTRACT,
            "valid": False,
            "outcome": outcome,
            "status": "invalid",
            "reason": "invalid resume marker contract",
        }

    outcome = runtime_resume_marker["outcome"]
    return {
        "contract": _SUMMARY_CONTRACT,
        "valid": True,
        "outcome": outcome,
        "status": "valid",
        "reason": None,
    }
