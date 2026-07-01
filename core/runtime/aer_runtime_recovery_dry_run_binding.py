"""Dry-run Runtime Recovery single-entry binding reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_event_route import (
    RECOVERY_CANONICAL_EVENT_CONTRACT,
    RECOVERY_EVENT_ROUTE_REPORT_CONTRACT,
)
from core.runtime.aer_runtime_recovery_kill_switch import RECOVERY_KILL_SWITCH_REPORT_CONTRACT


RECOVERY_DRY_RUN_BINDING_REPORT_CONTRACT = "aer.runtime.recovery.dry_run_binding_report.v1"
RECOVERY_DRY_RUN_BINDING_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_DRY_RUN_BINDING_ENTRY = "runtime_recovery_single_entry"
RECOVERY_DRY_RUN_BINDING_DENIED_CAPABILITIES = (
    "recovery_execution",
    "recovery_enablement",
    "runtime_mainline_wiring",
    "multi_entry_binding",
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
    "real_runtime_event_emission",
    "subprocess_call",
    "file_io",
)

__all__ = [
    "RECOVERY_DRY_RUN_BINDING_REPORT_CONTRACT",
    "RECOVERY_DRY_RUN_BINDING_ALLOWED_STATUSES",
    "RECOVERY_DRY_RUN_BINDING_ENTRY",
    "RECOVERY_DRY_RUN_BINDING_DENIED_CAPABILITIES",
    "prepare_recovery_dry_run_binding_report",
]


def prepare_recovery_dry_run_binding_report(
    event_route_report: Mapping[str, Any],
    kill_switch_report: Mapping[str, Any],
    *,
    binding_id: str | None = None,
    requested_status: str = "prepared",
    requested_entry: str = RECOVERY_DRY_RUN_BINDING_ENTRY,
    request_enablement: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare deterministic dry-run binding data without binding Recovery."""

    route = _plain_mapping(event_route_report)
    kill_switch = _plain_mapping(kill_switch_report)
    single_entry = requested_entry == RECOVERY_DRY_RUN_BINDING_ENTRY
    valid = _valid_route(route) and _valid_kill_switch(kill_switch) and single_entry
    denied = request_enablement or requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_DRY_RUN_BINDING_REPORT_CONTRACT,
        "binding_id": binding_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "dry_run": True,
        "single_entry_only": True,
        "binding_entry": RECOVERY_DRY_RUN_BINDING_ENTRY if single_entry else None,
        "bound_to_runtime": False,
        "binding_enabled": False,
        "route_enabled": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "canonical_event": _plain_mapping(route.get("canonical_event")) if _valid_route(route) else {},
        "event_route_reference": route if _valid_route(route) else {},
        "kill_switch_reference": kill_switch if _valid_kill_switch(kill_switch) else {},
        "denied_capabilities": list(RECOVERY_DRY_RUN_BINDING_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, single_entry, request_enablement),
        "metadata": _plain_mapping(metadata),
        "binding_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_route(value: Mapping[str, Any]) -> bool:
    event = _plain_mapping(value.get("canonical_event"))
    return (
        value.get("contract") == RECOVERY_EVENT_ROUTE_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("route_entry") == RECOVERY_DRY_RUN_BINDING_ENTRY
        and value.get("single_entry_only") is True
        and value.get("route_count") == 1
        and value.get("route_enabled") is False
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and event.get("contract") == RECOVERY_CANONICAL_EVENT_CONTRACT
        and event.get("entry_id") == RECOVERY_DRY_RUN_BINDING_ENTRY
        and event.get("event_emitted") is False
        and value.get("route_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _valid_kill_switch(value: Mapping[str, Any]) -> bool:
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
        and value.get("kill_switch_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool, single_entry: bool, request_enablement: bool) -> str | None:
    if request_enablement:
        return "Recovery enablement is prohibited during dry-run binding"
    if requested_status == "denied":
        return "caller requested passive denied dry-run binding status"
    if not single_entry:
        return "dry-run binding allows only runtime_recovery_single_entry"
    if not valid:
        return "missing or incompatible passive Recovery binding references"
    if requested_status == "blocked":
        return "caller requested passive blocked dry-run binding status"
    if requested_status != "prepared":
        return f"unsupported passive dry-run binding status: {requested_status}"
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
