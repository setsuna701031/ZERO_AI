"""Passive Runtime Recovery controlled activation preparation reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_wiring_gate import RECOVERY_WIRING_GATE_REPORT_CONTRACT


RECOVERY_CONTROLLED_ACTIVATION_REPORT_CONTRACT = "aer.runtime.recovery.controlled_activation_report.v1"
RECOVERY_CONTROLLED_ACTIVATION_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_CONTROLLED_ACTIVATION_DENIED_CAPABILITIES = (
    "activate_recovery",
    "runtime_mainline_wiring",
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
    "RECOVERY_CONTROLLED_ACTIVATION_REPORT_CONTRACT",
    "RECOVERY_CONTROLLED_ACTIVATION_ALLOWED_STATUSES",
    "RECOVERY_CONTROLLED_ACTIVATION_DENIED_CAPABILITIES",
    "prepare_recovery_controlled_activation",
]


def prepare_recovery_controlled_activation(
    wiring_gate_report: Mapping[str, Any],
    *,
    preparation_id: str | None = None,
    requested_status: str = "prepared",
    request_activation: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare controlled activation data while leaving activation disabled."""

    gate = _plain_mapping(wiring_gate_report)
    valid = _valid_gate(gate)
    denied = request_activation or requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_CONTROLLED_ACTIVATION_REPORT_CONTRACT,
        "preparation_id": preparation_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "activation_gate_enabled": False,
        "activation_allowed": False,
        "runtime_mainline_wiring_allowed": False,
        "wiring_gate_reference": gate if valid else {},
        "scheduler_adapter_reference": _plain_mapping(gate.get("scheduler_adapter_reference")) if valid else {},
        "operator_adapter_reference": _plain_mapping(gate.get("operator_adapter_reference")) if valid else {},
        "supervisor_adapter_reference": _plain_mapping(gate.get("supervisor_adapter_reference")) if valid else {},
        "native_adapter_reference": _plain_mapping(gate.get("native_adapter_reference")) if valid else {},
        "denied_capabilities": list(RECOVERY_CONTROLLED_ACTIVATION_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, request_activation),
        "metadata": _plain_mapping(metadata),
        "preparation_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_gate(value: Mapping[str, Any]) -> bool:
    return (
        value.get("contract") == RECOVERY_WIRING_GATE_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("activation_gate_enabled") is False
        and value.get("activation_allowed") is False
        and value.get("wiring_allowed") is False
        and value.get("gate_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool, request_activation: bool) -> str | None:
    if request_activation:
        return "activation request is prohibited during controlled activation preparation"
    if requested_status == "denied":
        return "caller requested passive denied controlled activation status"
    if not valid:
        return "missing or incompatible passive Recovery wiring gate report"
    if requested_status == "blocked":
        return "caller requested passive blocked controlled activation status"
    if requested_status != "prepared":
        return f"unsupported passive controlled activation status: {requested_status}"
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
