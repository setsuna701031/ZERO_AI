"""Disabled Runtime Recovery binding admission reports.

Package 205 turns admission evaluation data into a final inert admission report.
It does not grant admission or apply any runtime binding.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_binding_admission import (
    RECOVERY_BINDING_ADMISSION_ENTRY,
    RECOVERY_BINDING_ADMISSION_EVALUATION_CONTRACT,
)


RECOVERY_BINDING_ADMISSION_REPORT_CONTRACT = "aer.runtime.recovery.binding_admission_report.v1"
RECOVERY_BINDING_ADMISSION_REPORT_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_BINDING_ADMISSION_REPORT_DENIED_CAPABILITIES = (
    "recovery_execution",
    "recovery_enablement",
    "runtime_mainline_wiring",
    "runtime_hook_registration",
    "runtime_binding_application",
    "binding_admission_grant",
    "route_activation",
    "event_emission",
    "scheduler_call",
    "operator_call",
    "dispatcher_call",
    "supervisor_call",
    "native_runtime_call",
    "runtime_mutation",
    "persistence_write",
    "replay_action",
    "audit_emission",
    "journal_event",
    "subprocess_call",
    "file_io",
)

__all__ = [
    "RECOVERY_BINDING_ADMISSION_REPORT_CONTRACT",
    "RECOVERY_BINDING_ADMISSION_REPORT_ALLOWED_STATUSES",
    "RECOVERY_BINDING_ADMISSION_REPORT_DENIED_CAPABILITIES",
    "prepare_recovery_binding_admission_report",
]


def prepare_recovery_binding_admission_report(
    binding_admission_evaluation: Mapping[str, Any],
    *,
    report_id: str | None = None,
    requested_status: str = "prepared",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare final disabled binding admission report data without admission."""

    evaluation = _plain_mapping(binding_admission_evaluation)
    valid = _valid_evaluation(evaluation)
    denied = requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_BINDING_ADMISSION_REPORT_CONTRACT,
        "report_id": report_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "single_entry_only": True,
        "binding_entry": RECOVERY_BINDING_ADMISSION_ENTRY if valid else None,
        "admission_reported": prepared,
        "admission_granted": False,
        "admission_allowed": False,
        "binding_admitted": False,
        "runtime_accepts_binding": False,
        "runtime_hook_registered": False,
        "runtime_binding_applied": False,
        "binding_enabled": False,
        "recovery_enabled": False,
        "event_emitted": False,
        "canonical_event": _plain_mapping(evaluation.get("canonical_event")) if valid else {},
        "binding_admission_evaluation_reference": evaluation if valid else {},
        "denied_capabilities": list(RECOVERY_BINDING_ADMISSION_REPORT_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid),
        "metadata": _plain_mapping(metadata),
        "admission_report_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_evaluation(value: Mapping[str, Any]) -> bool:
    event = _plain_mapping(value.get("canonical_event"))
    return (
        value.get("contract") == RECOVERY_BINDING_ADMISSION_EVALUATION_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("single_entry_only") is True
        and value.get("binding_entry") == RECOVERY_BINDING_ADMISSION_ENTRY
        and value.get("admission_evaluated") is True
        and value.get("admission_allowed") is False
        and value.get("binding_admitted") is False
        and value.get("runtime_accepts_binding") is False
        and value.get("runtime_hook_registered") is False
        and value.get("runtime_binding_applied") is False
        and value.get("binding_enabled") is False
        and value.get("recovery_enabled") is False
        and value.get("event_emitted") is False
        and event.get("contract") == "aer.runtime.recovery.event.v1"
        and event.get("entry_id") == RECOVERY_BINDING_ADMISSION_ENTRY
        and event.get("event_emitted") is False
        and value.get("admission_evaluation_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool) -> str | None:
    if requested_status == "denied":
        return "caller requested passive denied binding admission report status"
    if not valid:
        return "missing or incompatible Recovery binding admission evaluation"
    if requested_status == "blocked":
        return "caller requested passive blocked binding admission report status"
    if requested_status != "prepared":
        return f"unsupported passive binding admission report status: {requested_status}"
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
