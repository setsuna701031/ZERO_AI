"""Disabled Runtime Recovery binding endpoint reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_binding_admission_report import (
    RECOVERY_BINDING_ADMISSION_REPORT_CONTRACT,
)


RECOVERY_BINDING_ENDPOINT_REPORT_CONTRACT = "aer.runtime.recovery.binding_endpoint_report.v1"
RECOVERY_BINDING_ENDPOINT_NAME = "runtime_recovery_binding_endpoint"
RECOVERY_BINDING_ENDPOINT_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_BINDING_ENDPOINT_DENIED_CAPABILITIES = (
    "recovery_execution",
    "recovery_enablement",
    "runtime_mainline_wiring",
    "runtime_hook_registration",
    "runtime_binding_application",
    "endpoint_activation",
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
    "RECOVERY_BINDING_ENDPOINT_REPORT_CONTRACT",
    "RECOVERY_BINDING_ENDPOINT_NAME",
    "RECOVERY_BINDING_ENDPOINT_ALLOWED_STATUSES",
    "RECOVERY_BINDING_ENDPOINT_DENIED_CAPABILITIES",
    "prepare_recovery_binding_endpoint_report",
]


def prepare_recovery_binding_endpoint_report(
    binding_admission_report: Mapping[str, Any],
    *,
    endpoint_id: str | None = None,
    requested_status: str = "prepared",
    requested_endpoint: str = RECOVERY_BINDING_ENDPOINT_NAME,
    request_activation: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare a disabled endpoint report without binding Recovery to runtime."""

    admission = _plain_mapping(binding_admission_report)
    endpoint_allowed = requested_endpoint == RECOVERY_BINDING_ENDPOINT_NAME
    valid = _valid_admission(admission) and endpoint_allowed
    denied = request_activation or requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_BINDING_ENDPOINT_REPORT_CONTRACT,
        "endpoint_id": endpoint_id,
        "endpoint_name": RECOVERY_BINDING_ENDPOINT_NAME if endpoint_allowed else None,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "endpoint_declared": True,
        "endpoint_enabled": False,
        "endpoint_invokable": False,
        "binding_disabled": True,
        "binding_applied": False,
        "runtime_hook_registered": False,
        "runtime_mainline_wiring_enabled": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "admission_granted": False,
        "binding_admission_reference": admission if _valid_admission(admission) else {},
        "denied_capabilities": list(RECOVERY_BINDING_ENDPOINT_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, endpoint_allowed, request_activation),
        "metadata": _plain_mapping(metadata),
        "endpoint_report_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_admission(value: Mapping[str, Any]) -> bool:
    return (
        value.get("contract") == RECOVERY_BINDING_ADMISSION_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("admission_granted") is False
        and value.get("runtime_binding_accepted") is False
        and value.get("binding_applied") is False
        and value.get("runtime_hook_registered") is False
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool, endpoint_allowed: bool, request_activation: bool) -> str | None:
    if request_activation:
        return "endpoint activation is prohibited while Recovery binding remains disabled"
    if requested_status == "denied":
        return "caller requested passive denied binding endpoint status"
    if not endpoint_allowed:
        return "binding endpoint allows only runtime_recovery_binding_endpoint"
    if not valid:
        return "missing or incompatible Recovery binding admission report"
    if requested_status == "blocked":
        return "caller requested passive blocked binding endpoint status"
    if requested_status != "prepared":
        return f"unsupported passive binding endpoint status: {requested_status}"
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
