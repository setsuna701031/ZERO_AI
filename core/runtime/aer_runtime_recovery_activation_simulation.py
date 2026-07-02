"""Disabled Runtime Recovery activation simulation reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_activation_gate_report import (
    RECOVERY_ACTIVATION_GATE_DECISION_REPORT_CONTRACT,
)


RECOVERY_ACTIVATION_SIMULATION_REPORT_CONTRACT = "aer.runtime.recovery.activation_simulation.v1"
RECOVERY_ACTIVATION_SIMULATION_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_ACTIVATION_SIMULATION_DENIED_CAPABILITIES = (
    "recovery_execution",
    "recovery_enablement",
    "runtime_mainline_wiring",
    "runtime_hook_registration",
    "runtime_binding_application",
    "endpoint_invocation",
    "activation_gate_opening",
    "activation_grant",
    "activation_simulation_apply",
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
    "RECOVERY_ACTIVATION_SIMULATION_REPORT_CONTRACT",
    "RECOVERY_ACTIVATION_SIMULATION_ALLOWED_STATUSES",
    "RECOVERY_ACTIVATION_SIMULATION_DENIED_CAPABILITIES",
    "prepare_recovery_activation_simulation",
]


def prepare_recovery_activation_simulation(
    activation_gate_report: Mapping[str, Any],
    *,
    simulation_id: str | None = None,
    requested_status: str = "prepared",
    request_simulation_apply: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare a non-applying activation simulation while Recovery remains disabled."""

    gate_report = _plain_mapping(activation_gate_report)
    valid = _valid_activation_gate_report(gate_report)
    denied = request_simulation_apply or requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_ACTIVATION_SIMULATION_REPORT_CONTRACT,
        "simulation_id": simulation_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "simulation_declared": True,
        "simulation_only": True,
        "simulation_applied": False,
        "simulation_result": "not_applied",
        "activation_gate_report_reference": gate_report if valid else {},
        "activation_state": "disabled",
        "gate_state": "closed",
        "gate_open": False,
        "gate_enabled": False,
        "activation_granted": False,
        "activation_allowed": False,
        "recovery_enabled": False,
        "binding_disabled": True,
        "binding_applied": False,
        "runtime_hook_registered": False,
        "runtime_mainline_wiring_enabled": False,
        "endpoint_invoked": False,
        "event_emitted": False,
        "kill_switch_required": True,
        "admission_required": True,
        "single_entry_only": True,
        "denied_capabilities": list(RECOVERY_ACTIVATION_SIMULATION_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, request_simulation_apply),
        "metadata": _plain_mapping(metadata),
        "activation_simulation_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_activation_gate_report(value: Mapping[str, Any]) -> bool:
    return (
        value.get("contract") == RECOVERY_ACTIVATION_GATE_DECISION_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("gate_report_prepared") is True
        and value.get("activation_state") == "disabled"
        and value.get("gate_state") == "closed"
        and value.get("gate_open") is False
        and value.get("gate_enabled") is False
        and value.get("activation_granted") is False
        and value.get("activation_allowed") is False
        and value.get("recovery_enabled") is False
        and value.get("binding_disabled") is True
        and value.get("binding_applied") is False
        and value.get("runtime_hook_registered") is False
        and value.get("runtime_mainline_wiring_enabled") is False
        and value.get("endpoint_invoked") is False
        and value.get("event_emitted") is False
        and value.get("kill_switch_required") is True
        and value.get("admission_required") is True
        and value.get("single_entry_only") is True
        and value.get("activation_report_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool, request_simulation_apply: bool) -> str | None:
    if request_simulation_apply:
        return "activation simulation application is prohibited while Runtime Recovery remains disabled"
    if requested_status == "denied":
        return "caller requested passive denied activation simulation status"
    if not valid:
        return "missing or incompatible closed Recovery activation gate report"
    if requested_status == "blocked":
        return "caller requested passive blocked activation simulation status"
    if requested_status != "prepared":
        return f"unsupported passive activation simulation status: {requested_status}"
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
