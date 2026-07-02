"""Disabled Runtime Recovery activation gate reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RECOVERY_BINDING_ENDPOINT_INVOCATION_REPORT_CONTRACT = "aer.runtime.recovery.binding_endpoint_invocation_report.v1"
RECOVERY_BINDING_ENDPOINT_NAME = "runtime_recovery_binding_endpoint"
RECOVERY_ACTIVATION_GATE_REPORT_CONTRACT = "aer.runtime.recovery.activation_gate.v1"
RECOVERY_ACTIVATION_GATE_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_ACTIVATION_GATE_DENIED_CAPABILITIES = (
    "recovery_execution",
    "recovery_enablement",
    "runtime_mainline_wiring",
    "runtime_hook_registration",
    "runtime_binding_application",
    "endpoint_invocation",
    "activation_gate_opening",
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
    "RECOVERY_BINDING_ENDPOINT_NAME",
    "RECOVERY_ACTIVATION_GATE_REPORT_CONTRACT",
    "RECOVERY_ACTIVATION_GATE_ALLOWED_STATUSES",
    "RECOVERY_ACTIVATION_GATE_DENIED_CAPABILITIES",
    "prepare_recovery_activation_gate",
]


def prepare_recovery_activation_gate(
    binding_endpoint_invocation_report: Mapping[str, Any],
    *,
    gate_id: str | None = None,
    requested_status: str = "prepared",
    request_gate_open: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare a closed activation gate without opening Runtime Recovery."""

    invocation = _plain_mapping(binding_endpoint_invocation_report)
    valid = _valid_invocation(invocation)
    denied = request_gate_open or requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_ACTIVATION_GATE_REPORT_CONTRACT,
        "gate_id": gate_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "gate_name": "runtime_recovery_activation_gate",
        "gate_declared": True,
        "gate_enabled": False,
        "gate_open": False,
        "activation_allowed": False,
        "activation_gate_enabled": False,
        "activation_gate_opened": False,
        "kill_switch_required": True,
        "admission_required": True,
        "endpoint_invocation_required": True,
        "endpoint_invoked": False,
        "endpoint_invokable": False,
        "binding_disabled": True,
        "binding_applied": False,
        "runtime_hook_registered": False,
        "runtime_mainline_wiring_enabled": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "single_entry_only": True,
        "endpoint_name": RECOVERY_BINDING_ENDPOINT_NAME if valid else None,
        "binding_endpoint_invocation_reference": invocation if valid else {},
        "denied_capabilities": list(RECOVERY_ACTIVATION_GATE_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, request_gate_open),
        "metadata": _plain_mapping(metadata),
        "activation_gate_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_invocation(value: Mapping[str, Any]) -> bool:
    return (
        value.get("contract") == RECOVERY_BINDING_ENDPOINT_INVOCATION_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("endpoint_name") == RECOVERY_BINDING_ENDPOINT_NAME
        and value.get("endpoint_declared") is True
        and value.get("endpoint_enabled") is False
        and value.get("endpoint_invokable") is False
        and value.get("endpoint_invoked") is False
        and value.get("invocation_allowed") is False
        and value.get("binding_disabled") is True
        and value.get("binding_applied") is False
        and value.get("runtime_hook_registered") is False
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool, request_gate_open: bool) -> str | None:
    if request_gate_open:
        return "activation gate opening is prohibited while Runtime Recovery remains disabled"
    if requested_status == "denied":
        return "caller requested passive denied activation gate status"
    if not valid:
        return "missing or incompatible disabled binding endpoint invocation report"
    if requested_status == "blocked":
        return "caller requested passive blocked activation gate status"
    if requested_status != "prepared":
        return f"unsupported passive activation gate status: {requested_status}"
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
