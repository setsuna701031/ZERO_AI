"""Passive Runtime Recovery event route preparation reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_controlled_activation import RECOVERY_CONTROLLED_ACTIVATION_REPORT_CONTRACT
from core.runtime.aer_runtime_recovery_kill_switch import RECOVERY_KILL_SWITCH_REPORT_CONTRACT


RECOVERY_EVENT_ROUTE_REPORT_CONTRACT = "aer.runtime.recovery.event_route_report.v1"
RECOVERY_CANONICAL_EVENT_CONTRACT = "aer.runtime.recovery.canonical_event.v1"
RECOVERY_EVENT_ROUTE_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_EVENT_ROUTE_DENIED_CAPABILITIES = (
    "event_emission",
    "recovery_execution",
    "recovery_enablement",
    "runtime_mainline_wiring",
    "multi_entry_wiring",
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
    "RECOVERY_EVENT_ROUTE_REPORT_CONTRACT",
    "RECOVERY_CANONICAL_EVENT_CONTRACT",
    "RECOVERY_EVENT_ROUTE_ALLOWED_STATUSES",
    "RECOVERY_EVENT_ROUTE_DENIED_CAPABILITIES",
    "prepare_recovery_event_route_report",
]


def prepare_recovery_event_route_report(
    controlled_activation_report: Mapping[str, Any],
    kill_switch_report: Mapping[str, Any],
    *,
    route_id: str | None = None,
    requested_status: str = "prepared",
    requested_entry: str = "runtime_recovery_single_entry",
    source_surface: str = "runtime_recovery_single_entry",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare a deterministic single-entry event route report without emitting events."""

    controlled = _plain_mapping(controlled_activation_report)
    kill_switch = _plain_mapping(kill_switch_report)
    single_entry = requested_entry == "runtime_recovery_single_entry"
    valid = _valid_controlled_activation(controlled) and _valid_kill_switch(kill_switch, controlled) and single_entry
    denied = requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"
    canonical_event = {
        "contract": RECOVERY_CANONICAL_EVENT_CONTRACT,
        "source_surface": source_surface,
        "entry_id": requested_entry if single_entry else None,
        "route_id": route_id,
        "gate_state": _gate_state(controlled),
        "event_emitted": False,
    }

    return {
        "contract": RECOVERY_EVENT_ROUTE_REPORT_CONTRACT,
        "route_id": route_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "route_entry": "runtime_recovery_single_entry" if single_entry else None,
        "single_entry_only": True,
        "route_count": 1 if single_entry else 0,
        "route_enabled": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "canonical_event": canonical_event,
        "controlled_activation_reference": controlled if _valid_controlled_activation(controlled) else {},
        "kill_switch_reference": kill_switch if _valid_kill_switch(kill_switch, controlled) else {},
        "denied_capabilities": list(RECOVERY_EVENT_ROUTE_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, single_entry),
        "metadata": _plain_mapping(metadata),
        "route_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_controlled_activation(value: Mapping[str, Any]) -> bool:
    return (
        value.get("contract") == RECOVERY_CONTROLLED_ACTIVATION_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("activation_gate_enabled") is False
        and value.get("activation_allowed") is False
        and value.get("runtime_mainline_wiring_allowed") is False
        and value.get("preparation_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _valid_kill_switch(value: Mapping[str, Any], controlled: Mapping[str, Any]) -> bool:
    return (
        value.get("contract") == RECOVERY_KILL_SWITCH_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("kill_switch_enabled") is False
        and value.get("kill_switch_state") == "off"
        and value.get("safe_mode") is True
        and value.get("recovery_enabled") is False
        and value.get("controlled_activation_reference") == controlled
        and value.get("kill_switch_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _gate_state(controlled: Mapping[str, Any]) -> str | None:
    gate = _plain_mapping(controlled.get("wiring_gate_reference"))
    value = gate.get("status")
    return value if isinstance(value, str) else None


def _reason(requested_status: str, valid: bool, single_entry: bool) -> str | None:
    if requested_status == "denied":
        return "caller requested passive denied event-route status"
    if not single_entry:
        return "event route preparation allows only runtime_recovery_single_entry"
    if not valid:
        return "missing or incompatible passive Recovery route references"
    if requested_status == "blocked":
        return "caller requested passive blocked event-route status"
    if requested_status != "prepared":
        return f"unsupported passive event-route status: {requested_status}"
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
