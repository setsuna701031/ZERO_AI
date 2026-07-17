from __future__ import annotations

import copy
from typing import Any, Dict

from core.runtime.aer_operator_composition_flow import (
    operator_flow_to_summary as _operator_flow_to_summary,
)

__all__ = [
    "create_operator_state",
    "validate_operator_state",
    "operator_state_to_summary",
]


_CONTRACT = "aer.operator_state.v2"
_OUTCOMES = ("continue", "approval_required", "issue_reported", "stopped")


def create_operator_state(*, composition_summary: Any) -> Dict[str, Any]:
    summary = _operator_flow_to_summary(composition_summary if isinstance(composition_summary, dict) else {})

    return {
        "contract": _CONTRACT,
        "outcome": summary.get("outcome"),
        "composition_summary": copy.deepcopy(summary),
    }


def validate_operator_state(payload: Any) -> Dict[str, Any]:
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
    if "composition_summary" not in payload:
        errors.append("missing required field: composition_summary")

    if payload.get("contract") != _CONTRACT:
        errors.append("invalid contract")

    if payload.get("outcome") not in _OUTCOMES:
        errors.append(f"invalid outcome: {payload.get('outcome')}")

    summary = payload.get("composition_summary")
    if not isinstance(summary, dict):
        errors.append("composition_summary must be a dict")
    else:
        normalized = _operator_flow_to_summary(summary)
        if summary != normalized:
            errors.append("composition_summary must match operator flow summary")
        if summary.get("outcome") != payload.get("outcome"):
            errors.append("outcome must match composition_summary outcome")

    return {
        "ok": not errors,
        "contract": _CONTRACT,
        "errors": errors,
    }


def operator_state_to_summary(operator_state: dict) -> Dict[str, Any]:
    return {
        "outcome": operator_state.get("outcome"),
        "composition_summary": _operator_flow_to_summary(
            operator_state.get("composition_summary") or {}
        ),
    }
