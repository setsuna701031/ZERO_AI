from __future__ import annotations

import copy
from typing import Any, Dict


def create_issue(
    *,
    issue_id: str,
    operator_session_id: str,
    package_id: str,
    severity: str,
    title: str,
    description: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "contract": "aer.operator_issue_reporter.v2",
        "issue_id": str(issue_id or ""),
        "operator_session_id": str(operator_session_id or ""),
        "package_id": str(package_id or ""),
        "severity": str(severity or ""),
        "status": "open",
        "title": str(title or ""),
        "description": str(description or ""),
        "metadata": dict(metadata or {}),
    }


def close_issue(issue: dict) -> Dict[str, Any]:
    updated = copy.deepcopy(dict(issue or {}))
    updated["status"] = "resolved"
    return updated


def validate_issue(payload: Any) -> Dict[str, Any]:
    contract = "aer.operator_issue_reporter.v2"
    required_fields = (
        "contract",
        "issue_id",
        "operator_session_id",
        "package_id",
        "severity",
        "status",
        "title",
        "description",
        "metadata",
    )
    severities = ("info", "warning", "error", "critical")
    statuses = ("open", "resolved", "dismissed")
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

    if payload.get("severity") not in severities:
        errors.append(f"invalid severity: {payload.get('severity')}")

    if payload.get("status") not in statuses:
        errors.append(f"invalid status: {payload.get('status')}")

    if not isinstance(payload.get("metadata"), dict):
        errors.append("metadata must be a dict")

    return {
        "ok": not errors,
        "contract": contract,
        "errors": errors,
    }


def issue_to_summary(issue: dict) -> Dict[str, Any]:
    return {
        "issue_id": issue.get("issue_id"),
        "severity": issue.get("severity"),
        "status": issue.get("status"),
        "title": issue.get("title"),
    }
