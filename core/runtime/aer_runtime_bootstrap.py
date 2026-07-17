from __future__ import annotations

import copy
from typing import Any, Dict

from core.runtime.aer_runtime_intake import (
    runtime_intake_to_summary as _runtime_intake_to_summary,
    validate_runtime_intake as _validate_runtime_intake,
)

__all__ = [
    "create_runtime_bootstrap",
    "validate_runtime_bootstrap",
    "runtime_bootstrap_to_summary",
]


_CONTRACT = "aer.runtime_bootstrap.v2"
_OUTCOMES = ("continue", "approval_required", "issue_reported", "stopped")
_BOOTSTRAP_FIELDS = frozenset(("contract", "outcome", "runtime_intake", "valid", "errors"))


def create_runtime_bootstrap(*, runtime_intake: Any) -> Dict[str, Any]:
    validation = _validate_runtime_intake(runtime_intake)
    source = runtime_intake if isinstance(runtime_intake, dict) else {}
    intake_summary = _runtime_intake_to_summary(source)
    source_valid = validation["valid"]
    outcome = intake_summary.get("outcome") if source_valid else "issue_reported"

    return {
        "contract": _CONTRACT,
        "outcome": outcome,
        "runtime_intake": copy.deepcopy(intake_summary),
        "valid": source_valid,
        "errors": copy.deepcopy(validation["errors"]),
    }


def validate_runtime_bootstrap(payload: Any) -> Dict[str, Any]:
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
    if "runtime_intake" not in payload:
        errors.append("missing required field: runtime_intake")
    if "valid" not in payload:
        errors.append("missing required field: valid")
    if "errors" not in payload:
        errors.append("missing required field: errors")

    if set(payload) != _BOOTSTRAP_FIELDS:
        errors.append("bootstrap fields must match declared contract")

    if payload.get("contract") != _CONTRACT:
        errors.append("invalid contract")

    if payload.get("outcome") not in _OUTCOMES:
        errors.append(f"invalid outcome: {payload.get('outcome')}")

    intake_summary = payload.get("runtime_intake")
    if not isinstance(intake_summary, dict):
        errors.append("runtime_intake must be a dict")
    else:
        normalized = _runtime_intake_to_summary(intake_summary)
        if intake_summary != normalized:
            errors.append("runtime_intake must match runtime intake summary")

    if not isinstance(payload.get("valid"), bool):
        errors.append("valid must be a bool")

    if not isinstance(payload.get("errors"), list):
        errors.append("errors must be a list")
    elif payload.get("valid") is True:
        if payload.get("errors"):
            errors.append("valid runtime bootstrap must not include errors")
        elif isinstance(intake_summary, dict) and intake_summary.get("outcome") != payload.get("outcome"):
            errors.append("outcome must match runtime_intake outcome")
    elif payload.get("valid") is False:
        if payload.get("outcome") != "issue_reported":
            errors.append("invalid runtime bootstrap must report issue")
        if not payload.get("errors"):
            errors.append("invalid runtime bootstrap must include errors")
        errors.append("runtime bootstrap contains invalid runtime intake")

    return {
        "valid": not errors,
        "contract": _CONTRACT,
        "errors": errors,
    }


def runtime_bootstrap_to_summary(bootstrap: dict) -> Dict[str, Any]:
    return {
        "outcome": bootstrap.get("outcome"),
        "runtime_intake": _runtime_intake_to_summary(bootstrap.get("runtime_intake") or {}),
        "valid": bootstrap.get("valid"),
    }
