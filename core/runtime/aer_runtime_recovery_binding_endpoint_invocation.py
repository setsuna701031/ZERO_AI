"""Disabled Runtime Recovery binding endpoint invocation reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_binding_endpoint import (
    RECOVERY_BINDING_ENDPOINT_NAME,
    RECOVERY_BINDING_ENDPOINT_REPORT_CONTRACT,
)


RECOVERY_BINDING_ENDPOINT_INVOCATION_REPORT_CONTRACT = "aer.runtime.recovery.binding_endpoint_invocation_report.v1"
RECOVERY_BINDING_ENDPOINT_INVOCATION_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_BINDING_ENDPOINT_INVOCATION_DENIED_CAPABILITIES = (
    "endpoint_invocation",
    "recovery_execution",
    "recovery_enablement",
    "runtime_mainline_wiring",
    "runtime_hook_registration",
    "runtime_binding_application",
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
    "RECOVERY_BINDING_ENDPOINT_INVOCATION_REPORT_CONTRACT",
    "RECOVERY_BINDING_ENDPOINT_INVOCATION_ALLOWED_STATUSES",
    "RECOVERY_BINDING_ENDPOINT_INVOCATION_DENIED_CAPABILITIES",
    "prepare_recovery_binding_endpoint_invocation_report",
]


def prepare_recovery_binding_endpoint_invocation_report(
    binding_endpoint_report: Mapping[str, Any],
    *,
    invocation_id: str | None = None,
    requested_status: str = "prepared",
    request_invocation: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe endpoint invocation readiness without invoking a runtime endpoint."""

    endpoint = _plain_mapping(binding_endpoint_report)
    valid = _valid_endpoint(endpoint)
    denied = request_invocation or requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_BINDING_ENDPOINT_INVOCATION_REPORT_CONTRACT,
        "invocation_id": invocation_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "endpoint_name": RECOVERY_BINDING_ENDPOINT_NAME if valid else None,
        "endpoint_declared": valid,
        "endpoint_enabled": False,
        "endpoint_invokable": False,
        "endpoint_invoked": False,
        "invocation_allowed": False,
        "binding_disabled": True,
        "binding_applied": False,
        "runtime_hook_registered": False,
        "runtime_mainline_wiring_enabled": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "binding_endpoint_reference": endpoint if valid else {},
        "denied_capabilities": list(RECOVERY_BINDING_ENDPOINT_INVOCATION_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, request_invocation),
        "metadata": _plain_mapping(metadata),
        "invocation_report_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_endpoint(value: Mapping[str, Any]) -> bool:
    return (
        value.get("contract") == RECOVERY_BINDING_ENDPOINT_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("endpoint_name") == RECOVERY_BINDING_ENDPOINT_NAME
        and value.get("endpoint_declared") is True
        and value.get("endpoint_enabled") is False
        and value.get("endpoint_invokable") is False
        and value.get("binding_disabled") is True
        and value.get("binding_applied") is False
        and value.get("runtime_hook_registered") is False
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool, request_invocation: bool) -> str | None:
    if request_invocation:
        return "endpoint invocation is prohibited while Runtime Recovery binding remains disabled"
    if requested_status == "denied":
        return "caller requested passive denied endpoint invocation status"
    if not valid:
        return "missing or incompatible disabled Recovery binding endpoint report"
    if requested_status == "blocked":
        return "caller requested passive blocked endpoint invocation status"
    if requested_status != "prepared":
        return f"unsupported passive endpoint invocation status: {requested_status}"
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
