from __future__ import annotations

import copy
from typing import Any, Dict


def create_plan(
    *,
    plan_id: str,
    operator_session_id: str,
    package_id: str,
    plan_type: str,
    plan_reason: str,
    created_at: str = "",
    steps: list[Dict[str, Any]] | None = None,
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "contract": "aer.operator_plan.v2",
        "plan_id": str(plan_id or ""),
        "operator_session_id": str(operator_session_id or ""),
        "package_id": str(package_id or ""),
        "plan_type": str(plan_type or ""),
        "plan_reason": str(plan_reason or ""),
        "status": "proposed",
        "steps": copy.deepcopy(list(steps or [])),
        "metadata": dict(metadata or {}),
        "created_at": str(created_at or ""),
    }


def validate_plan(payload: Any) -> Dict[str, Any]:
    contract = "aer.operator_plan.v2"
    required_fields = (
        "contract",
        "plan_id",
        "operator_session_id",
        "package_id",
        "plan_type",
        "plan_reason",
        "status",
        "steps",
        "metadata",
        "created_at",
    )
    plan_types = (
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

    if not str(payload.get("plan_id") or "").strip():
        errors.append("plan_id is required")

    if not str(payload.get("operator_session_id") or "").strip():
        errors.append("operator_session_id is required")

    if not str(payload.get("package_id") or "").strip():
        errors.append("package_id is required")

    if payload.get("plan_type") not in plan_types:
        errors.append(f"invalid plan_type: {payload.get('plan_type')}")

    if not str(payload.get("plan_reason") or "").strip():
        errors.append("plan_reason is required")

    if payload.get("status") not in statuses:
        errors.append(f"invalid status: {payload.get('status')}")

    if not isinstance(payload.get("steps"), list):
        errors.append("steps must be a list")

    if not isinstance(payload.get("metadata"), dict):
        errors.append("metadata must be a dict")

    return {
        "ok": not errors,
        "contract": contract,
        "errors": errors,
    }


def accept_plan(plan: dict, *, accepted_by: str | None = None) -> Dict[str, Any]:
    updated = copy.deepcopy(dict(plan or {}))
    updated["status"] = "accepted"
    if accepted_by is not None:
        updated["accepted_by"] = str(accepted_by)
    return updated


def plan_to_summary(plan: dict) -> Dict[str, Any]:
    return {
        "plan_id": plan.get("plan_id"),
        "plan_type": plan.get("plan_type"),
        "status": plan.get("status"),
        "plan_reason": plan.get("plan_reason"),
    }
