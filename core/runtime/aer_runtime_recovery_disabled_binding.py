"""Disabled Runtime Recovery binding skeleton reports.

Package 200 keeps Runtime Recovery binding represented as inert contract data.
It does not register hooks, emit events, call runtime surfaces, or execute Recovery.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RECOVERY_DISABLED_RUNTIME_BINDING_REPORT_CONTRACT = (
    "aer.runtime.recovery.disabled_runtime_binding_report.v1"
)
RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY = "runtime_recovery_single_entry"
RECOVERY_DISABLED_RUNTIME_BINDING_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_DISABLED_RUNTIME_BINDING_DENIED_CAPABILITIES = (
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
    "RECOVERY_DISABLED_RUNTIME_BINDING_REPORT_CONTRACT",
    "RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY",
    "RECOVERY_DISABLED_RUNTIME_BINDING_ALLOWED_STATUSES",
    "RECOVERY_DISABLED_RUNTIME_BINDING_DENIED_CAPABILITIES",
    "prepare_recovery_disabled_runtime_binding_report",
]


def prepare_recovery_disabled_runtime_binding_report(
    binding_approval_report: Mapping[str, Any],
    *,
    binding_id: str | None = None,
    requested_status: str = "prepared",
    requested_entry: str = RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare disabled Runtime Recovery binding data without binding runtime."""

    approval = _plain_mapping(binding_approval_report)
    single_entry = requested_entry == RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY
    valid = _valid_approval(approval) and single_entry
    denied = requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_DISABLED_RUNTIME_BINDING_REPORT_CONTRACT,
        "binding_id": binding_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "single_entry_only": True,
        "binding_entry": RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY if single_entry else None,
        "binding_skeleton": True,
        "binding_enabled": False,
        "bound_to_runtime": False,
        "runtime_hook_registered": False,
        "runtime_binding_applied": False,
        "runtime_mainline_wiring_enabled": False,
        "kill_switch_state": "off",
        "recovery_enabled": False,
        "event_emitted": False,
        "canonical_event": _plain_mapping(approval.get("canonical_event")) if _valid_approval(approval) else {},
        "binding_approval_reference": approval if _valid_approval(approval) else {},
        "denied_capabilities": list(RECOVERY_DISABLED_RUNTIME_BINDING_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, single_entry),
        "metadata": _plain_mapping(metadata),
        "disabled_binding_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_approval(value: Mapping[str, Any]) -> bool:
    event = _plain_mapping(value.get("canonical_event"))
    return (
        value.get("contract") == "aer.runtime.recovery.binding_approval_report.v1"
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("approval_granted") is False
        and value.get("binding_allowed") is False
        and value.get("binding_enabled") is False
        and value.get("runtime_binding_applied") is False
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and event.get("contract") == "aer.runtime.recovery.event.v1"
        and event.get("entry_id") == RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY
        and event.get("event_emitted") is False
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool, single_entry: bool) -> str | None:
    if requested_status == "denied":
        return "caller requested passive denied disabled binding status"
    if not single_entry:
        return "disabled binding allows only runtime_recovery_single_entry"
    if not valid:
        return "missing or incompatible Recovery binding approval report"
    if requested_status == "blocked":
        return "caller requested passive blocked disabled binding status"
    if requested_status != "prepared":
        return f"unsupported passive disabled binding status: {requested_status}"
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
