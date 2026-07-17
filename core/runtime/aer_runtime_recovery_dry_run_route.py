"""Dry-run Runtime Recovery route integration reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_dry_run_binding import (
    RECOVERY_DRY_RUN_BINDING_ENTRY,
    RECOVERY_DRY_RUN_BINDING_REPORT_CONTRACT,
)
from core.runtime.aer_runtime_recovery_event_route import (
    RECOVERY_CANONICAL_EVENT_CONTRACT,
    RECOVERY_EVENT_ROUTE_REPORT_CONTRACT,
)


RECOVERY_DRY_RUN_ROUTE_REPORT_CONTRACT = "aer.runtime.recovery.dry_run_route_report.v1"
RECOVERY_DRY_RUN_ROUTE_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_DRY_RUN_ROUTE_DENIED_CAPABILITIES = (
    "recovery_execution",
    "recovery_enablement",
    "runtime_mainline_wiring",
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
    "RECOVERY_DRY_RUN_ROUTE_REPORT_CONTRACT",
    "RECOVERY_DRY_RUN_ROUTE_ALLOWED_STATUSES",
    "RECOVERY_DRY_RUN_ROUTE_DENIED_CAPABILITIES",
    "prepare_recovery_dry_run_route_report",
]


def prepare_recovery_dry_run_route_report(
    dry_run_binding_report: Mapping[str, Any],
    event_route_report: Mapping[str, Any],
    *,
    dry_run_route_id: str | None = None,
    requested_status: str = "prepared",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare deterministic dry-run route integration data without routing runtime."""

    binding = _plain_mapping(dry_run_binding_report)
    route = _plain_mapping(event_route_report)
    valid = _valid_binding(binding) and _valid_route(route) and binding.get("event_route_reference") == route
    denied = requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_DRY_RUN_ROUTE_REPORT_CONTRACT,
        "dry_run_route_id": dry_run_route_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "dry_run": True,
        "route_integrated": False,
        "single_entry_only": True,
        "route_entry": RECOVERY_DRY_RUN_BINDING_ENTRY if valid else None,
        "binding_enabled": False,
        "route_enabled": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "canonical_event": _plain_mapping(route.get("canonical_event")) if _valid_route(route) else {},
        "dry_run_binding_reference": binding if _valid_binding(binding) else {},
        "event_route_reference": route if _valid_route(route) else {},
        "denied_capabilities": list(RECOVERY_DRY_RUN_ROUTE_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid),
        "metadata": _plain_mapping(metadata),
        "route_report_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_binding(value: Mapping[str, Any]) -> bool:
    event = _plain_mapping(value.get("canonical_event"))
    return (
        value.get("contract") == RECOVERY_DRY_RUN_BINDING_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("dry_run") is True
        and value.get("single_entry_only") is True
        and value.get("binding_entry") == RECOVERY_DRY_RUN_BINDING_ENTRY
        and value.get("bound_to_runtime") is False
        and value.get("binding_enabled") is False
        and value.get("route_enabled") is False
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and event.get("contract") == RECOVERY_CANONICAL_EVENT_CONTRACT
        and event.get("entry_id") == RECOVERY_DRY_RUN_BINDING_ENTRY
        and event.get("event_emitted") is False
        and value.get("binding_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _valid_route(value: Mapping[str, Any]) -> bool:
    event = _plain_mapping(value.get("canonical_event"))
    return (
        value.get("contract") == RECOVERY_EVENT_ROUTE_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("route_entry") == RECOVERY_DRY_RUN_BINDING_ENTRY
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


def _reason(requested_status: str, valid: bool) -> str | None:
    if requested_status == "denied":
        return "caller requested passive denied dry-run route status"
    if not valid:
        return "missing or incompatible passive Recovery dry-run route references"
    if requested_status == "blocked":
        return "caller requested passive blocked dry-run route status"
    if requested_status != "prepared":
        return f"unsupported passive dry-run route status: {requested_status}"
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
