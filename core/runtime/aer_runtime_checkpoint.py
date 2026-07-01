from __future__ import annotations

from typing import Any, Dict

from core.runtime.aer_runtime_lifecycle import (
    runtime_lifecycle_to_summary as _runtime_lifecycle_to_summary,
    validate_runtime_lifecycle as _validate_runtime_lifecycle,
)

__all__ = [
    "create_runtime_checkpoint",
    "validate_runtime_checkpoint",
    "runtime_checkpoint_to_summary",
]


_CONTRACT = "aer.runtime_checkpoint.v2"
_OUTCOMES = ("continue", "approval_required", "issue_reported", "stopped")
_CHECKPOINT_FIELDS = frozenset(("outcome", "source_outcome", "source_valid"))
_RUNTIME_CHECKPOINT_FIELDS = frozenset(("contract", "outcome", "runtime_checkpoint", "valid", "errors"))
_FIELD_PURPOSES = {
    "contract": "schema identifier",
    "outcome": "runtime-visible checkpoint result",
    "runtime_checkpoint": "minimal runtime checkpoint marker",
    "valid": "structural validity of this checkpoint contract",
    "errors": "structural validation errors",
}
_CHECKPOINT_FIELD_PURPOSES = {
    "outcome": "runtime-visible checkpoint result",
    "source_outcome": "runtime-visible upstream result projected into this checkpoint",
    "source_valid": "structural validity of the upstream contract",
}


def _upstream_errors(validation: Dict[str, Any]) -> list[str]:
    if validation.get("valid") is True:
        return []
    return ["invalid upstream contract"]


def _build_runtime_checkpoint(*, outcome: Any, source_outcome: Any, source_valid: bool) -> Dict[str, Any]:
    return {
        "outcome": outcome,
        "source_outcome": source_outcome,
        "source_valid": source_valid,
    }


def create_runtime_checkpoint(*, runtime_lifecycle: Any) -> Dict[str, Any]:
    validation = _validate_runtime_lifecycle(runtime_lifecycle)
    source_valid = validation["valid"]
    source_summary = _runtime_lifecycle_to_summary(
        runtime_lifecycle if isinstance(runtime_lifecycle, dict) else {}
    )
    source_outcome = source_summary.get("outcome")
    outcome = source_outcome if source_valid else "issue_reported"

    return {
        "contract": _CONTRACT,
        "outcome": outcome,
        "runtime_checkpoint": _build_runtime_checkpoint(
            outcome=outcome,
            source_outcome=source_outcome,
            source_valid=source_valid,
        ),
        "valid": source_valid,
        "errors": _upstream_errors(validation),
    }


def validate_runtime_checkpoint(payload: Any) -> Dict[str, Any]:
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
    if "runtime_checkpoint" not in payload:
        errors.append("missing required field: runtime_checkpoint")
    if "valid" not in payload:
        errors.append("missing required field: valid")
    if "errors" not in payload:
        errors.append("missing required field: errors")

    if set(payload) != _RUNTIME_CHECKPOINT_FIELDS:
        errors.append("runtime checkpoint fields must match declared contract")

    if payload.get("contract") != _CONTRACT:
        errors.append("invalid contract")

    if payload.get("outcome") not in _OUTCOMES:
        errors.append(f"invalid outcome: {payload.get('outcome')}")

    marker = payload.get("runtime_checkpoint")
    if not isinstance(marker, dict):
        errors.append("runtime_checkpoint must be a dict")
    else:
        if set(marker) != _CHECKPOINT_FIELDS:
            errors.append("runtime_checkpoint fields must match declared contract")

        if marker.get("outcome") not in _OUTCOMES:
            errors.append(f"invalid runtime_checkpoint outcome: {marker.get('outcome')}")
        elif marker.get("outcome") != payload.get("outcome"):
            errors.append("outcome must match runtime_checkpoint outcome")

        if marker.get("source_outcome") not in _OUTCOMES:
            errors.append(f"invalid runtime_checkpoint source_outcome: {marker.get('source_outcome')}")
        elif marker.get("source_valid") is True and marker.get("source_outcome") != payload.get("outcome"):
            errors.append("source_outcome must match outcome when source is valid")

        if not isinstance(marker.get("source_valid"), bool):
            errors.append("runtime_checkpoint source_valid must be a bool")
        elif isinstance(payload.get("valid"), bool) and marker.get("source_valid") != payload.get("valid"):
            errors.append("runtime_checkpoint source_valid must match valid")

    if not isinstance(payload.get("valid"), bool):
        errors.append("valid must be a bool")

    if not isinstance(payload.get("errors"), list):
        errors.append("errors must be a list")
    elif payload.get("valid") is True:
        if payload.get("errors"):
            errors.append("valid runtime checkpoint must not include errors")
    elif payload.get("valid") is False:
        if payload.get("outcome") != "issue_reported":
            errors.append("invalid runtime checkpoint must report issue")
        if not payload.get("errors"):
            errors.append("invalid runtime checkpoint must include errors")
        errors.append("runtime checkpoint contains invalid upstream contract")

    return {
        "valid": not errors,
        "contract": _CONTRACT,
        "errors": errors,
    }


def runtime_checkpoint_to_summary(runtime_checkpoint: dict) -> Dict[str, Any]:
    marker = runtime_checkpoint.get("runtime_checkpoint") if isinstance(runtime_checkpoint, dict) else {}
    if not isinstance(marker, dict):
        marker = {}

    return {
        "outcome": runtime_checkpoint.get("outcome") if isinstance(runtime_checkpoint, dict) else None,
        "runtime_checkpoint": _build_runtime_checkpoint(
            outcome=marker.get("outcome"),
            source_outcome=marker.get("source_outcome"),
            source_valid=marker.get("source_valid") is True,
        ),
        "valid": runtime_checkpoint.get("valid") if isinstance(runtime_checkpoint, dict) else None,
    }
