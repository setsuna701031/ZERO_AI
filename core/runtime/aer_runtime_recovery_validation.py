"""Pure Runtime Recovery public contract validation helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RECOVERY_ELIGIBILITY_CONTRACT = "aer.runtime.recovery.eligibility.v1"
RECOVERY_PLAN_CONTRACT = "aer.runtime.recovery.plan.v1"
RECOVERY_EXECUTION_BOUNDARY_CONTRACT = "aer.runtime.recovery.execution_boundary.v1"

ELIGIBILITY_REQUIRED_FIELDS = frozenset(
    {
        "contract",
        "eligible",
        "blocked",
        "status",
        "reason",
        "execution_summary",
        "failure_classification",
        "recovery_authorized",
        "descriptive_only",
    }
)

PLAN_REQUIRED_FIELDS = frozenset(
    {
        "contract",
        "recovery_token",
        "eligible",
        "status",
        "reason",
        "execution_summary",
        "failure_classification",
        "plan_steps",
        "execution_boundary",
        "metadata",
        "descriptive_only",
    }
)

EXECUTION_BOUNDARY_REQUIRED_FIELDS = frozenset(
    {
        "contract",
        "execution_allowed",
        "future_domain_only",
        "downstream_authorized",
        "reason",
    }
)

ALLOWED_ELIGIBILITY_STATUSES = frozenset(
    {
        "eligible",
        "blocked",
        "invalid_execution_summary",
        "invalid_recovery_request",
        "recovery_not_authorized",
        "scheduler_required",
        "operator_required",
        "persistence_required",
        "audit_required",
        "journal_required",
    }
)

ALLOWED_PLAN_STATUSES = frozenset(
    {
        "planned",
        "blocked",
        "invalid_execution_summary",
        "invalid_recovery_request",
        "recovery_not_authorized",
        "scheduler_required",
        "operator_required",
        "persistence_required",
        "audit_required",
        "journal_required",
    }
)

__all__ = [
    "RECOVERY_ELIGIBILITY_CONTRACT",
    "RECOVERY_PLAN_CONTRACT",
    "RECOVERY_EXECUTION_BOUNDARY_CONTRACT",
    "ELIGIBILITY_REQUIRED_FIELDS",
    "PLAN_REQUIRED_FIELDS",
    "EXECUTION_BOUNDARY_REQUIRED_FIELDS",
    "ALLOWED_ELIGIBILITY_STATUSES",
    "ALLOWED_PLAN_STATUSES",
    "validate_recovery_eligibility",
    "validate_recovery_plan",
    "validate_recovery_execution_boundary",
]


def validate_recovery_eligibility(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a Recovery Eligibility payload without side effects."""

    if not isinstance(payload, Mapping):
        return _report("Compatibility Error", "recovery eligibility must be a mapping")
    data = dict(payload)
    if data.get("contract") != RECOVERY_ELIGIBILITY_CONTRACT:
        return _report("Compatibility Error", "invalid recovery eligibility contract")
    field_report = _validate_fields(data, ELIGIBILITY_REQUIRED_FIELDS, "recovery eligibility")
    if field_report is not None:
        return field_report
    shared_report = _validate_shared_recovery_fields(data, ALLOWED_ELIGIBILITY_STATUSES, "recovery eligibility")
    if shared_report is not None:
        return shared_report
    if not isinstance(data.get("blocked"), bool):
        return _report("Status Error", "invalid blocked flag")
    if data.get("eligible") is True and data.get("blocked") is True:
        return _report("Status Error", "eligible and blocked conflict")
    if not isinstance(data.get("recovery_authorized"), bool):
        return _report("Execution Boundary Error", "invalid recovery authorization flag")
    return _report(None, None)


def validate_recovery_plan(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a Recovery Plan payload without side effects."""

    if not isinstance(payload, Mapping):
        return _report("Compatibility Error", "recovery plan must be a mapping")
    data = dict(payload)
    if data.get("contract") != RECOVERY_PLAN_CONTRACT:
        return _report("Compatibility Error", "invalid recovery plan contract")
    field_report = _validate_fields(data, PLAN_REQUIRED_FIELDS, "recovery plan")
    if field_report is not None:
        return field_report
    shared_report = _validate_shared_recovery_fields(data, ALLOWED_PLAN_STATUSES, "recovery plan")
    if shared_report is not None:
        return shared_report
    if not _non_empty_text(data.get("recovery_token")):
        return _report("Identity Error", "invalid recovery token")
    if not _descriptive_text_list(data.get("plan_steps")):
        return _report("Compatibility Error", "invalid plan steps")
    boundary_report = validate_recovery_execution_boundary(data.get("execution_boundary"))
    if boundary_report.get("valid") is not True:
        return _report("Execution Boundary Error", "invalid recovery execution boundary")
    if not isinstance(data.get("metadata"), Mapping):
        return _report("Compatibility Error", "invalid metadata")
    return _report(None, None)


def validate_recovery_execution_boundary(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a Recovery Execution Boundary payload without side effects."""

    if not isinstance(payload, Mapping):
        return _report("Compatibility Error", "recovery execution boundary must be a mapping")
    data = dict(payload)
    if data.get("contract") != RECOVERY_EXECUTION_BOUNDARY_CONTRACT:
        return _report("Compatibility Error", "invalid recovery execution boundary contract")
    field_report = _validate_fields(data, EXECUTION_BOUNDARY_REQUIRED_FIELDS, "recovery execution boundary")
    if field_report is not None:
        return field_report
    if data.get("execution_allowed") is not False:
        return _report("Execution Boundary Error", "recovery execution boundary cannot allow execution")
    if data.get("future_domain_only") is not True:
        return _report("Execution Boundary Error", "recovery execution boundary must remain future-domain only")
    if data.get("downstream_authorized") is not False:
        return _report("Execution Boundary Error", "recovery execution boundary cannot authorize downstream")
    if data.get("reason") is not None and not isinstance(data.get("reason"), str):
        return _report("Compatibility Error", "invalid recovery execution boundary reason")
    return _report(None, None)


def _validate_shared_recovery_fields(
    data: Mapping[str, Any], allowed_statuses: frozenset[str], label: str
) -> dict[str, Any] | None:
    if not isinstance(data.get("eligible"), bool):
        return _report("Status Error", "invalid eligible flag")
    if data.get("status") not in allowed_statuses:
        return _report("Status Error", f"invalid {label} status")
    if data.get("reason") is not None and not isinstance(data.get("reason"), str):
        return _report("Compatibility Error", f"invalid {label} reason")
    if not isinstance(data.get("execution_summary"), Mapping):
        return _report("Compatibility Error", "invalid execution summary")
    if data.get("failure_classification") is not None and not isinstance(data.get("failure_classification"), str):
        return _report("Compatibility Error", "invalid failure classification")
    if data.get("descriptive_only") is not True:
        return _report("Execution Boundary Error", f"{label} must be descriptive only")
    return None


def _validate_fields(data: Mapping[str, Any], required: frozenset[str], label: str) -> dict[str, Any] | None:
    fields = set(data)
    if not required <= fields:
        return _report("Compatibility Error", f"missing {label} fields")
    if fields != required:
        return _report("Compatibility Error", f"unknown {label} fields")
    return None


def _non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _descriptive_text_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(_non_empty_text(item) for item in value)


def _report(category: str | None, reason: str | None) -> dict[str, Any]:
    return {
        "valid": category is None,
        "category": category,
        "reason": reason,
        "auto_repair_allowed": False,
        "descriptive_only": True,
    }
