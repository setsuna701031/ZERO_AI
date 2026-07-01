"""Passive Runtime Recovery binding registry reports.

The registry is contract data only. It describes the single allowed binding point
for future Recovery wiring while keeping Recovery disabled and unbound.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_preflight import RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT


RECOVERY_BINDING_REGISTRY_REPORT_CONTRACT = "aer.runtime.recovery.binding_registry.v1"
RECOVERY_BINDING_REGISTRY_ENTRY = "runtime_recovery_single_entry"
RECOVERY_BINDING_REGISTRY_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_BINDING_REGISTRY_DENIED_CAPABILITIES = (
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
    "RECOVERY_BINDING_REGISTRY_REPORT_CONTRACT",
    "RECOVERY_BINDING_REGISTRY_ENTRY",
    "RECOVERY_BINDING_REGISTRY_ALLOWED_STATUSES",
    "RECOVERY_BINDING_REGISTRY_DENIED_CAPABILITIES",
    "prepare_recovery_binding_registry_report",
]


def prepare_recovery_binding_registry_report(
    preflight_eligibility: Mapping[str, Any],
    *,
    registry_id: str | None = None,
    requested_status: str = "prepared",
    requested_entry: str = RECOVERY_BINDING_REGISTRY_ENTRY,
    request_activation: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare passive binding registry data without registering runtime hooks."""

    preflight = _plain_mapping(preflight_eligibility)
    single_entry = requested_entry == RECOVERY_BINDING_REGISTRY_ENTRY
    valid = _valid_preflight(preflight) and single_entry
    denied = request_activation or requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_BINDING_REGISTRY_REPORT_CONTRACT,
        "registry_id": registry_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "binding_registry_only": True,
        "registry_entry": RECOVERY_BINDING_REGISTRY_ENTRY if single_entry else None,
        "single_entry_only": True,
        "registry_declared": prepared,
        "runtime_binding_registered": False,
        "runtime_binding_active": False,
        "runtime_mainline_wiring_allowed": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "canonical_event": _plain_mapping(preflight.get("canonical_event")) if _valid_preflight(preflight) else {},
        "preflight_reference": preflight if _valid_preflight(preflight) else {},
        "denied_capabilities": list(RECOVERY_BINDING_REGISTRY_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, single_entry, request_activation),
        "metadata": _plain_mapping(metadata),
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_preflight(value: Mapping[str, Any]) -> bool:
    event = _plain_mapping(value.get("canonical_event"))
    return (
        value.get("contract") == RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("preflight_only") is True
        and value.get("eligible") is True
        and value.get("runtime_binding_allowed") is False
        and value.get("runtime_mainline_wiring_allowed") is False
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and event.get("event_emitted") is False
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool, single_entry: bool, request_activation: bool) -> str | None:
    if request_activation:
        return "runtime binding activation is prohibited by passive registry semantics"
    if requested_status == "denied":
        return "caller requested passive denied binding registry status"
    if not single_entry:
        return "binding registry allows only runtime_recovery_single_entry"
    if not valid:
        return "missing or incompatible Recovery preflight eligibility report"
    if requested_status == "blocked":
        return "caller requested passive blocked binding registry status"
    if requested_status != "prepared":
        return f"unsupported passive binding registry status: {requested_status}"
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
