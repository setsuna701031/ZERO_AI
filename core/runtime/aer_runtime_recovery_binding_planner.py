"""Passive Runtime Recovery binding plan reports.

The planner composes preflight eligibility and the passive binding registry into a
future wiring plan. It never binds, activates, emits, mutates, or calls runtime.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_binding_registry import (
    RECOVERY_BINDING_REGISTRY_ENTRY,
    RECOVERY_BINDING_REGISTRY_REPORT_CONTRACT,
)
from core.runtime.aer_runtime_recovery_preflight import RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT


RECOVERY_BINDING_PLAN_REPORT_CONTRACT = "aer.runtime.recovery.binding_plan.v1"
RECOVERY_BINDING_PLAN_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_BINDING_PLAN_DENIED_CAPABILITIES = (
    "recovery_execution",
    "recovery_enablement",
    "runtime_mainline_wiring",
    "runtime_binding_activation",
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
    "RECOVERY_BINDING_PLAN_REPORT_CONTRACT",
    "RECOVERY_BINDING_PLAN_ALLOWED_STATUSES",
    "RECOVERY_BINDING_PLAN_DENIED_CAPABILITIES",
    "prepare_recovery_binding_plan_report",
]


def prepare_recovery_binding_plan_report(
    registry_report: Mapping[str, Any],
    preflight_eligibility: Mapping[str, Any],
    *,
    plan_id: str | None = None,
    requested_status: str = "prepared",
    request_binding_activation: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare a passive Recovery binding plan without applying it."""

    registry = _plain_mapping(registry_report)
    preflight = _plain_mapping(preflight_eligibility)
    valid = _valid_registry(registry) and _valid_preflight(preflight) and registry.get("preflight_reference") == preflight
    denied = request_binding_activation or requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_BINDING_PLAN_REPORT_CONTRACT,
        "plan_id": plan_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "binding_plan_only": True,
        "plan_state": "planned" if prepared else "denied" if denied else "blocked",
        "binding_entry": RECOVERY_BINDING_REGISTRY_ENTRY if valid else None,
        "single_entry_only": True,
        "binding_planned": prepared,
        "binding_applied": False,
        "runtime_binding_registered": False,
        "runtime_binding_active": False,
        "runtime_mainline_wiring_allowed": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "canonical_event": _plain_mapping(preflight.get("canonical_event")) if _valid_preflight(preflight) else {},
        "registry_reference": registry if _valid_registry(registry) else {},
        "preflight_reference": preflight if _valid_preflight(preflight) else {},
        "denied_capabilities": list(RECOVERY_BINDING_PLAN_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, request_binding_activation),
        "metadata": _plain_mapping(metadata),
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_registry(value: Mapping[str, Any]) -> bool:
    event = _plain_mapping(value.get("canonical_event"))
    return (
        value.get("contract") == RECOVERY_BINDING_REGISTRY_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("binding_registry_only") is True
        and value.get("registry_entry") == RECOVERY_BINDING_REGISTRY_ENTRY
        and value.get("runtime_binding_registered") is False
        and value.get("runtime_binding_active") is False
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and event.get("event_emitted") is False
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _valid_preflight(value: Mapping[str, Any]) -> bool:
    event = _plain_mapping(value.get("canonical_event"))
    return (
        value.get("contract") == RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("eligible") is True
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and event.get("event_emitted") is False
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool, request_binding_activation: bool) -> str | None:
    if request_binding_activation:
        return "runtime binding activation is prohibited during passive planning"
    if requested_status == "denied":
        return "caller requested passive denied binding plan status"
    if not valid:
        return "missing or incompatible Recovery binding registry or preflight references"
    if requested_status == "blocked":
        return "caller requested passive blocked binding plan status"
    if requested_status != "prepared":
        return f"unsupported passive binding plan status: {requested_status}"
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
