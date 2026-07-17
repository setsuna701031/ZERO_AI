"""Passive Runtime Recovery binding policy reports.

This module intentionally defines policy data only. It does not bind Recovery
to any runtime surface, emit events, mutate runtime state, or call scheduler,
operator, supervisor, dispatcher, native runtime, persistence, replay, audit,
journal, subprocess, or filesystem behavior.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RECOVERY_RUNTIME_BINDING_POLICY_CONTRACT = "aer.runtime.recovery.binding_policy.v1"
RECOVERY_RUNTIME_BINDING_POLICY_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_RUNTIME_BINDING_POLICY_ENTRY = "runtime_recovery_single_entry"
RECOVERY_RUNTIME_BINDING_POLICY_ALLOWED_SURFACES = (
    "runtime_recovery_single_entry",
)
RECOVERY_RUNTIME_BINDING_POLICY_OBSERVE_ONLY_SURFACES = (
    "scheduler",
    "operator",
    "supervisor",
    "native_runtime",
)
RECOVERY_RUNTIME_BINDING_POLICY_DENIED_CAPABILITIES = (
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
    "RECOVERY_RUNTIME_BINDING_POLICY_CONTRACT",
    "RECOVERY_RUNTIME_BINDING_POLICY_ALLOWED_STATUSES",
    "RECOVERY_RUNTIME_BINDING_POLICY_ENTRY",
    "RECOVERY_RUNTIME_BINDING_POLICY_ALLOWED_SURFACES",
    "RECOVERY_RUNTIME_BINDING_POLICY_OBSERVE_ONLY_SURFACES",
    "RECOVERY_RUNTIME_BINDING_POLICY_DENIED_CAPABILITIES",
    "prepare_recovery_runtime_binding_policy",
]


def prepare_recovery_runtime_binding_policy(
    *,
    requested_entry: str = RECOVERY_RUNTIME_BINDING_POLICY_ENTRY,
    requested_status: str = "prepared",
    request_enablement: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare passive binding policy data without binding runtime."""

    single_entry = requested_entry == RECOVERY_RUNTIME_BINDING_POLICY_ENTRY
    denied = request_enablement or requested_status == "denied"
    prepared = single_entry and requested_status == "prepared" and not denied
    blocked = ((not single_entry) and not denied) or (single_entry and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_RUNTIME_BINDING_POLICY_CONTRACT,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "binding_policy_only": True,
        "binding_entry": RECOVERY_RUNTIME_BINDING_POLICY_ENTRY if single_entry else None,
        "single_entry_only": True,
        "allowed_surfaces": list(RECOVERY_RUNTIME_BINDING_POLICY_ALLOWED_SURFACES),
        "observe_only_surfaces": list(RECOVERY_RUNTIME_BINDING_POLICY_OBSERVE_ONLY_SURFACES),
        "binds_runtime": False,
        "binding_enabled": False,
        "route_enabled": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "activation_allowed": False,
        "runtime_mainline_wiring_allowed": False,
        "denied_capabilities": list(RECOVERY_RUNTIME_BINDING_POLICY_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, single_entry, request_enablement),
        "metadata": _plain_mapping(metadata),
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _reason(requested_status: str, single_entry: bool, request_enablement: bool) -> str | None:
    if request_enablement:
        return "Recovery enablement is prohibited by passive binding policy"
    if requested_status == "denied":
        return "caller requested passive denied binding policy status"
    if not single_entry:
        return "binding policy allows only runtime_recovery_single_entry"
    if requested_status == "blocked":
        return "caller requested passive blocked binding policy status"
    if requested_status != "prepared":
        return f"unsupported passive binding policy status: {requested_status}"
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
