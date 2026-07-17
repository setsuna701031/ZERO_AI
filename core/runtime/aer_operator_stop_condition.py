from __future__ import annotations

import copy
from typing import Any, Dict


def create_stop_condition(
    *,
    stop_condition_id: str,
    operator_session_id: str,
    package_id: str,
    reason: str,
    message: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "contract": "aer.operator_stop_condition.v2",
        "stop_condition_id": str(stop_condition_id or ""),
        "operator_session_id": str(operator_session_id or ""),
        "package_id": str(package_id or ""),
        "reason": str(reason or ""),
        "status": "active",
        "message": str(message or ""),
        "metadata": dict(metadata or {}),
    }


def resolve_stop_condition(
    stop_condition: dict,
    *,
    resolved_by: str | None = None,
    resolution_note: str | None = None,
) -> Dict[str, Any]:
    updated = copy.deepcopy(dict(stop_condition or {}))
    updated["status"] = "resolved"
    if resolved_by is not None:
        updated["resolved_by"] = str(resolved_by)
    if resolution_note is not None:
        updated["resolution_note"] = str(resolution_note)
    return updated


def validate_stop_condition(payload: Any) -> Dict[str, Any]:
    contract = "aer.operator_stop_condition.v2"
    required_fields = (
        "contract",
        "stop_condition_id",
        "operator_session_id",
        "package_id",
        "reason",
        "status",
        "message",
        "metadata",
    )
    reasons = (
        "completed",
        "failed",
        "blocked",
        "waiting_for_approval",
        "validation_failed",
        "unsafe_to_continue",
        "checkpoint_missing",
        "checkpoint_invalid",
        "resume_identity_mismatch",
        "non_mainline_issue_detected",
    )
    statuses = ("active", "resolved")
    errors = []

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "contract": contract,
            "errors": ["payload must be a dict"],
        }

    for field in required_fields:
        if field not in payload:
            errors.append(f"missing required field: {field}")

    if payload.get("contract") != contract:
        errors.append("invalid contract")

    if not str(payload.get("stop_condition_id") or "").strip():
        errors.append("stop_condition_id is required")

    if not str(payload.get("operator_session_id") or "").strip():
        errors.append("operator_session_id is required")

    if not str(payload.get("package_id") or "").strip():
        errors.append("package_id is required")

    if payload.get("reason") not in reasons:
        errors.append(f"invalid reason: {payload.get('reason')}")

    if payload.get("status") not in statuses:
        errors.append(f"invalid status: {payload.get('status')}")

    if not isinstance(payload.get("metadata"), dict):
        errors.append("metadata must be a dict")

    return {
        "ok": not errors,
        "contract": contract,
        "errors": errors,
    }


def stop_condition_to_summary(stop_condition: dict) -> Dict[str, Any]:
    return {
        "stop_condition_id": stop_condition.get("stop_condition_id"),
        "reason": stop_condition.get("reason"),
        "status": stop_condition.get("status"),
        "message": stop_condition.get("message"),
    }
