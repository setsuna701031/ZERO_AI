"""Observe-only Runtime Recovery surface probe reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_dry_run_binding import RECOVERY_DRY_RUN_BINDING_ENTRY
from core.runtime.aer_runtime_recovery_dry_run_route import RECOVERY_DRY_RUN_ROUTE_REPORT_CONTRACT
from core.runtime.aer_runtime_recovery_event_route import RECOVERY_CANONICAL_EVENT_CONTRACT


RECOVERY_SURFACE_PROBE_REPORT_CONTRACT = "aer.runtime.recovery.surface_probe_report.v1"
RECOVERY_SURFACE_PROBE_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_SURFACE_PROBE_DENIED_CAPABILITIES = (
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
    "RECOVERY_SURFACE_PROBE_REPORT_CONTRACT",
    "RECOVERY_SURFACE_PROBE_ALLOWED_STATUSES",
    "RECOVERY_SURFACE_PROBE_DENIED_CAPABILITIES",
    "prepare_recovery_surface_probe_report",
]


def prepare_recovery_surface_probe_report(
    dry_run_route_report: Mapping[str, Any],
    *,
    probe_id: str | None = None,
    requested_status: str = "prepared",
    requested_entry: str = RECOVERY_DRY_RUN_BINDING_ENTRY,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare deterministic observe-only surface probe data without probing runtime."""

    route = _plain_mapping(dry_run_route_report)
    single_entry = requested_entry == RECOVERY_DRY_RUN_BINDING_ENTRY
    valid = _valid_dry_run_route(route) and single_entry
    denied = requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_SURFACE_PROBE_REPORT_CONTRACT,
        "probe_id": probe_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "observe_only": True,
        "dry_run": True,
        "single_entry_only": True,
        "observation_entry": RECOVERY_DRY_RUN_BINDING_ENTRY if single_entry else None,
        "surface_probe_allowed": True,
        "surface_probe_executed": False,
        "runtime_surface_touched": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "canonical_event": _plain_mapping(route.get("canonical_event")) if _valid_dry_run_route(route) else {},
        "dry_run_route_reference": route if _valid_dry_run_route(route) else {},
        "denied_capabilities": list(RECOVERY_SURFACE_PROBE_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, single_entry),
        "metadata": _plain_mapping(metadata),
        "probe_report_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_dry_run_route(value: Mapping[str, Any]) -> bool:
    event = _plain_mapping(value.get("canonical_event"))
    return (
        value.get("contract") == RECOVERY_DRY_RUN_ROUTE_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("dry_run") is True
        and value.get("route_integrated") is False
        and value.get("single_entry_only") is True
        and value.get("route_entry") == RECOVERY_DRY_RUN_BINDING_ENTRY
        and value.get("binding_enabled") is False
        and value.get("route_enabled") is False
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and event.get("contract") == RECOVERY_CANONICAL_EVENT_CONTRACT
        and event.get("entry_id") == RECOVERY_DRY_RUN_BINDING_ENTRY
        and event.get("event_emitted") is False
        and value.get("route_report_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool, single_entry: bool) -> str | None:
    if requested_status == "denied":
        return "caller requested passive denied surface probe status"
    if not single_entry:
        return "surface probe allows only runtime_recovery_single_entry"
    if not valid:
        return "missing or incompatible passive Recovery dry-run route report"
    if requested_status == "blocked":
        return "caller requested passive blocked surface probe status"
    if requested_status != "prepared":
        return f"unsupported passive surface probe status: {requested_status}"
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
