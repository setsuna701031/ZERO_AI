"""Passive Runtime Recovery wiring gate reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_native_adapter import RECOVERY_NATIVE_ADAPTER_REPORT_CONTRACT
from core.runtime.aer_runtime_recovery_operator_adapter import RECOVERY_OPERATOR_ADAPTER_REPORT_CONTRACT
from core.runtime.aer_runtime_recovery_scheduler_adapter import RECOVERY_SCHEDULER_ADAPTER_REPORT_CONTRACT
from core.runtime.aer_runtime_recovery_supervisor_adapter import RECOVERY_SUPERVISOR_ADAPTER_REPORT_CONTRACT


RECOVERY_WIRING_GATE_REPORT_CONTRACT = "aer.runtime.recovery.wiring_gate_report.v1"
RECOVERY_WIRING_GATE_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_WIRING_GATE_DENIED_CAPABILITIES = (
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
    "RECOVERY_WIRING_GATE_REPORT_CONTRACT",
    "RECOVERY_WIRING_GATE_ALLOWED_STATUSES",
    "RECOVERY_WIRING_GATE_DENIED_CAPABILITIES",
    "prepare_recovery_wiring_gate_report",
]


def prepare_recovery_wiring_gate_report(
    scheduler_adapter_report: Mapping[str, Any],
    operator_adapter_report: Mapping[str, Any],
    supervisor_adapter_report: Mapping[str, Any],
    native_adapter_report: Mapping[str, Any],
    *,
    gate_id: str | None = None,
    requested_status: str = "prepared",
    enable_activation_gate: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare a passive gate report while keeping activation disabled."""

    scheduler = _plain_mapping(scheduler_adapter_report)
    operator = _plain_mapping(operator_adapter_report)
    supervisor = _plain_mapping(supervisor_adapter_report)
    native = _plain_mapping(native_adapter_report)
    valid = (
        _valid_adapter(scheduler, RECOVERY_SCHEDULER_ADAPTER_REPORT_CONTRACT, "scheduler")
        and _valid_adapter(operator, RECOVERY_OPERATOR_ADAPTER_REPORT_CONTRACT, "operator")
        and _valid_adapter(supervisor, RECOVERY_SUPERVISOR_ADAPTER_REPORT_CONTRACT, "runtime_supervisor")
        and _valid_adapter(native, RECOVERY_NATIVE_ADAPTER_REPORT_CONTRACT, "native_runtime")
    )
    denied = enable_activation_gate or requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_WIRING_GATE_REPORT_CONTRACT,
        "gate_id": gate_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "activation_gate_enabled": False,
        "activation_allowed": False,
        "wiring_allowed": False,
        "scheduler_adapter_reference": scheduler if _valid_adapter(scheduler, RECOVERY_SCHEDULER_ADAPTER_REPORT_CONTRACT, "scheduler") else {},
        "operator_adapter_reference": operator if _valid_adapter(operator, RECOVERY_OPERATOR_ADAPTER_REPORT_CONTRACT, "operator") else {},
        "supervisor_adapter_reference": supervisor if _valid_adapter(supervisor, RECOVERY_SUPERVISOR_ADAPTER_REPORT_CONTRACT, "runtime_supervisor") else {},
        "native_adapter_reference": native if _valid_adapter(native, RECOVERY_NATIVE_ADAPTER_REPORT_CONTRACT, "native_runtime") else {},
        "denied_capabilities": list(RECOVERY_WIRING_GATE_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, enable_activation_gate),
        "metadata": _plain_mapping(metadata),
        "gate_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_adapter(value: Mapping[str, Any], contract: str, target: str) -> bool:
    return (
        value.get("contract") == contract
        and value.get("adapter_target") == target
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("adapter_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool, enable_activation_gate: bool) -> str | None:
    if enable_activation_gate:
        return "activation gate enablement is prohibited in passive wiring gate"
    if requested_status == "denied":
        return "caller requested passive denied gate status"
    if not valid:
        return "missing or incompatible passive Recovery adapter references"
    if requested_status == "blocked":
        return "caller requested passive blocked gate status"
    if requested_status != "prepared":
        return f"unsupported passive gate status: {requested_status}"
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
