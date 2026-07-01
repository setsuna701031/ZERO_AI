"""Pure Runtime Recovery consumer-boundary reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime import aer_runtime_recovery_validation as _validation


RECOVERY_CONSUMER_BOUNDARY_CONTRACT = "aer.runtime.recovery.consumer_boundary.v1"

ALLOWED_RECOVERY_PLAN_CONSUMERS = frozenset(
    {
        "runtime_recovery_consumer_boundary",
        "runtime_recovery_closure_review",
        "runtime_recovery_integration_blueprint",
    }
)

RECOVERY_CONSUMER_ALLOWED_BOUNDARY = "descriptive_recovery_plan_only"

RECOVERY_CONSUMER_DENIED_CAPABILITIES = (
    "recovery_execution",
    "scheduler_admission",
    "dispatcher_command",
    "operator_action",
    "persistence_write",
    "audit_emission",
    "journal_event",
    "replay_action",
    "runtime_mutation",
    "file_mutation",
    "external_process_call",
)

__all__ = [
    "RECOVERY_CONSUMER_BOUNDARY_CONTRACT",
    "ALLOWED_RECOVERY_PLAN_CONSUMERS",
    "RECOVERY_CONSUMER_ALLOWED_BOUNDARY",
    "RECOVERY_CONSUMER_DENIED_CAPABILITIES",
    "describe_recovery_plan_consumption",
]


def describe_recovery_plan_consumption(
    recovery_plan: Mapping[str, Any],
    *,
    consumer_type: str,
) -> dict[str, Any]:
    """Describe whether a consumer may consume a Recovery Plan payload."""

    plan = _plain_mapping(recovery_plan)
    validation_report = _validation.validate_recovery_plan(plan)
    plan_valid = validation_report.get("valid") is True
    consumer_allowed = consumer_type in ALLOWED_RECOVERY_PLAN_CONSUMERS
    accepted = plan_valid and consumer_allowed

    return {
        "contract": RECOVERY_CONSUMER_BOUNDARY_CONTRACT,
        "accepted": accepted,
        "rejected": not accepted,
        "consumer_type": consumer_type,
        "allowed_boundary": RECOVERY_CONSUMER_ALLOWED_BOUNDARY if accepted else None,
        "denied_capabilities": list(RECOVERY_CONSUMER_DENIED_CAPABILITIES),
        "reason": _reason(plan_valid, consumer_allowed, validation_report),
        "plan_valid": plan_valid,
        "descriptive_only": True,
    }


def _reason(
    plan_valid: bool,
    consumer_allowed: bool,
    validation_report: Mapping[str, Any],
) -> str | None:
    if not plan_valid:
        return _text_or_none(validation_report.get("reason")) or "invalid recovery plan"
    if not consumer_allowed:
        return "unknown recovery plan consumer"
    return None


def _plain_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _plain_value(item) for key, item in value.items()}


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _plain_mapping(value)
    if isinstance(value, list):
        return [_plain_value(item) for item in value]
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    return value


def _text_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None
