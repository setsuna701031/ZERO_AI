from __future__ import annotations

import copy
from typing import Any, Dict, Tuple

AER_OPERATOR_APPROVAL_CONTRACT = "aer.operator_approval.v2"

APPROVAL_STATUSES: Tuple[str, ...] = (
    "pending",
    "approved",
    "rejected",
    "expired",
)

APPROVAL_REQUIRED_FIELDS: Tuple[str, ...] = (
    "contract",
    "approval_id",
    "operator_session_id",
    "package_id",
    "requested_action",
    "request_reason",
    "status",
    "metadata",
)


def create_approval_request(
    *,
    approval_id: str,
    operator_session_id: str,
    package_id: str,
    requested_action: str,
    request_reason: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "contract": AER_OPERATOR_APPROVAL_CONTRACT,
        "approval_id": str(approval_id or ""),
        "operator_session_id": str(operator_session_id or ""),
        "package_id": str(package_id or ""),
        "requested_action": str(requested_action or ""),
        "request_reason": str(request_reason or ""),
        "status": "pending",
        "metadata": dict(metadata or {}),
    }


def approve_request(approval: dict, *, approved_by: str | None = None) -> Dict[str, Any]:
    updated = copy.deepcopy(dict(approval or {}))
    updated["status"] = "approved"
    if approved_by is not None:
        updated["approved_by"] = str(approved_by)
    return updated


def reject_request(
    approval: dict,
    *,
    rejected_by: str | None = None,
    rejection_reason: str | None = None,
) -> Dict[str, Any]:
    updated = copy.deepcopy(dict(approval or {}))
    updated["status"] = "rejected"
    if rejected_by is not None:
        updated["rejected_by"] = str(rejected_by)
    if rejection_reason is not None:
        updated["rejection_reason"] = str(rejection_reason)
    return updated


def validate_approval(payload: Any) -> Dict[str, Any]:
    errors = []

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "contract": AER_OPERATOR_APPROVAL_CONTRACT,
            "errors": ["payload must be a dict"],
        }

    for field in APPROVAL_REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"missing required field: {field}")

    if payload.get("contract") != AER_OPERATOR_APPROVAL_CONTRACT:
        errors.append("invalid contract")

    if not str(payload.get("approval_id") or "").strip():
        errors.append("approval_id is required")

    if not str(payload.get("operator_session_id") or "").strip():
        errors.append("operator_session_id is required")

    if not str(payload.get("package_id") or "").strip():
        errors.append("package_id is required")

    if not str(payload.get("requested_action") or "").strip():
        errors.append("requested_action is required")

    if payload.get("status") not in APPROVAL_STATUSES:
        errors.append(f"invalid status: {payload.get('status')}")

    if not isinstance(payload.get("metadata"), dict):
        errors.append("metadata must be a dict")

    return {
        "ok": not errors,
        "contract": AER_OPERATOR_APPROVAL_CONTRACT,
        "errors": errors,
    }
