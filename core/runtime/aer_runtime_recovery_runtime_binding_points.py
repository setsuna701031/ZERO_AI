"""Disabled Runtime Recovery binding point inventory reports.

Package 201 describes eligible binding points as inert contract data only.
No binding point is registered with runtime and no runtime module is inspected.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_disabled_binding import (
    RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY,
    RECOVERY_DISABLED_RUNTIME_BINDING_REPORT_CONTRACT,
)


RECOVERY_RUNTIME_BINDING_POINTS_REPORT_CONTRACT = (
    "aer.runtime.recovery.runtime_binding_points_report.v1"
)
RECOVERY_RUNTIME_BINDING_POINTS_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_RUNTIME_BINDING_POINTS_DENIED_CAPABILITIES = (
    "recovery_execution",
    "recovery_enablement",
    "runtime_mainline_wiring",
    "runtime_hook_registration",
    "runtime_binding_application",
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
    "RECOVERY_RUNTIME_BINDING_POINTS_REPORT_CONTRACT",
    "RECOVERY_RUNTIME_BINDING_POINTS_ALLOWED_STATUSES",
    "RECOVERY_RUNTIME_BINDING_POINTS_DENIED_CAPABILITIES",
    "prepare_recovery_runtime_binding_points_report",
]


def prepare_recovery_runtime_binding_points_report(
    disabled_binding_report: Mapping[str, Any],
    *,
    binding_points_id: str | None = None,
    requested_status: str = "prepared",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare inert Runtime Recovery binding point data without runtime registration."""

    binding = _plain_mapping(disabled_binding_report)
    valid = _valid_disabled_binding(binding)
    denied = requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_RUNTIME_BINDING_POINTS_REPORT_CONTRACT,
        "binding_points_id": binding_points_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "single_entry_only": True,
        "binding_entry": RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY if valid else None,
        "binding_points_declared": prepared,
        "binding_points_registered": False,
        "runtime_hook_registered": False,
        "runtime_binding_applied": False,
        "runtime_surface_touched": False,
        "binding_enabled": False,
        "recovery_enabled": False,
        "event_emitted": False,
        "binding_points": [
            {
                "point_id": RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY,
                "surface": "runtime",
                "mode": "disabled",
                "registered": False,
                "calls_runtime": False,
                "emits_event": False,
                "executes_recovery": False,
            }
        ]
        if valid
        else [],
        "canonical_event": _plain_mapping(binding.get("canonical_event")) if valid else {},
        "disabled_binding_reference": binding if valid else {},
        "denied_capabilities": list(RECOVERY_RUNTIME_BINDING_POINTS_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid),
        "metadata": _plain_mapping(metadata),
        "binding_points_report_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_disabled_binding(value: Mapping[str, Any]) -> bool:
    event = _plain_mapping(value.get("canonical_event"))
    return (
        value.get("contract") == RECOVERY_DISABLED_RUNTIME_BINDING_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("single_entry_only") is True
        and value.get("binding_entry") == RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY
        and value.get("binding_skeleton") is True
        and value.get("binding_enabled") is False
        and value.get("bound_to_runtime") is False
        and value.get("runtime_hook_registered") is False
        and value.get("runtime_binding_applied") is False
        and value.get("runtime_mainline_wiring_enabled") is False
        and value.get("recovery_enabled") is False
        and value.get("event_emitted") is False
        and event.get("contract") == "aer.runtime.recovery.event.v1"
        and event.get("entry_id") == RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY
        and event.get("event_emitted") is False
        and value.get("disabled_binding_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool) -> str | None:
    if requested_status == "denied":
        return "caller requested passive denied binding-points status"
    if not valid:
        return "missing or incompatible disabled Runtime Recovery binding report"
    if requested_status == "blocked":
        return "caller requested passive blocked binding-points status"
    if requested_status != "prepared":
        return f"unsupported passive binding-points status: {requested_status}"
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
