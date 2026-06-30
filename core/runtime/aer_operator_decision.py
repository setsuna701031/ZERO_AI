from __future__ import annotations

import copy
from typing import Any, Dict


def create_decision(
    *,
    decision_id: str,
    operator_session_id: str,
    package_id: str,
    decision_type: str,
    decision_reason: str,
    created_at: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "contract": "aer.operator_decision.v2",
        "decision_id": str(decision_id or ""),
        "operator_session_id": str(operator_session_id or ""),
        "package_id": str(package_id or ""),
        "decision_type": str(decision_type or ""),
        "decision_reason": str(decision_reason or ""),
        "status": "proposed",
        "metadata": dict(metadata or {}),
        "created_at": str(created_at or ""),
    }


def validate_decision(payload: Any) -> Dict[str, Any]:
    contract = "aer.operator_decision.v2"
    required_fields = (
        "contract",
        "decision_id",
        "operator_session_id",
        "package_id",
        "decision_type",
        "decision_reason",
        "status",
        "metadata",
        "created_at",
    )
    decision_types = (
        "continue",
        "stop",
        "request_approval",
        "report_issue",
        "checkpoint",
        "resume",
    )
    statuses = ("proposed", "accepted", "rejected")
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

    if not str(payload.get("decision_id") or "").strip():
        errors.append("decision_id is required")

    if not str(payload.get("operator_session_id") or "").strip():
        errors.append("operator_session_id is required")

    if not str(payload.get("package_id") or "").strip():
        errors.append("package_id is required")

    if payload.get("decision_type") not in decision_types:
        errors.append(f"invalid decision_type: {payload.get('decision_type')}")

    if not str(payload.get("decision_reason") or "").strip():
        errors.append("decision_reason is required")

    if payload.get("status") not in statuses:
        errors.append(f"invalid status: {payload.get('status')}")

    if not isinstance(payload.get("metadata"), dict):
        errors.append("metadata must be a dict")

    return {
        "ok": not errors,
        "contract": contract,
        "errors": errors,
    }


def accept_decision(
    decision: dict,
    *,
    accepted_by: str | None = None,
) -> Dict[str, Any]:
    updated = copy.deepcopy(dict(decision or {}))
    updated["status"] = "accepted"
    if accepted_by is not None:
        updated["accepted_by"] = str(accepted_by)
    return updated


def decision_to_summary(decision: dict) -> Dict[str, Any]:
    return {
        "decision_id": decision.get("decision_id"),
        "decision_type": decision.get("decision_type"),
        "status": decision.get("status"),
        "decision_reason": decision.get("decision_reason"),
    }
