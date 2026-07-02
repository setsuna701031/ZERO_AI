"""Disabled canonical Runtime Recovery surface reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RECOVERY_CANONICAL_SURFACE_CONTRACT = "aer.runtime.recovery.canonical_surface.v1"
RECOVERY_CANONICAL_SURFACE_NAME = "runtime_recovery_canonical_surface"
RECOVERY_CANONICAL_SURFACE_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_CANONICAL_SURFACE_DENIED_CAPABILITIES = (
    "recovery_execution",
    "recovery_enablement",
    "runtime_mainline_wiring",
    "runtime_hook_registration",
    "runtime_binding_application",
    "endpoint_invocation",
    "event_emission",
    "scheduler_call",
    "taskrunner_call",
    "operator_call",
    "dispatcher_call",
    "supervisor_call",
    "native_runtime_call",
    "watchdog_call",
    "runtime_mutation",
    "persistence_write",
    "audit_emission",
    "journal_event",
    "subprocess_call",
    "filesystem_mutation",
)

__all__ = [
    "RECOVERY_CANONICAL_SURFACE_CONTRACT",
    "RECOVERY_CANONICAL_SURFACE_NAME",
    "RECOVERY_CANONICAL_SURFACE_ALLOWED_STATUSES",
    "RECOVERY_CANONICAL_SURFACE_DENIED_CAPABILITIES",
    "prepare_canonical_runtime_recovery_surface",
]


def prepare_canonical_runtime_recovery_surface(
    *,
    surface_id: str | None = None,
    requested_surface: str = RECOVERY_CANONICAL_SURFACE_NAME,
    requested_status: str = "prepared",
    request_activation: bool = False,
    request_execution: bool = False,
    request_hook_registration: bool = False,
    request_binding_application: bool = False,
    request_endpoint_invocation: bool = False,
    request_event_emission: bool = False,
    request_runtime_mutation: bool = False,
    request_persistence: bool = False,
    request_audit: bool = False,
    request_journal: bool = False,
    request_subprocess: bool = False,
    request_filesystem_mutation: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare the disabled canonical surface without wiring it into Runtime."""

    surface_allowed = requested_surface == RECOVERY_CANONICAL_SURFACE_NAME
    status_allowed = requested_status in RECOVERY_CANONICAL_SURFACE_ALLOWED_STATUSES
    denied = requested_status == "denied" or any(
        (
            request_activation,
            request_execution,
            request_hook_registration,
            request_binding_application,
            request_endpoint_invocation,
            request_event_emission,
            request_runtime_mutation,
            request_persistence,
            request_audit,
            request_journal,
            request_subprocess,
            request_filesystem_mutation,
        )
    )
    prepared = surface_allowed and status_allowed and requested_status == "prepared" and not denied
    blocked = not denied and (not surface_allowed or not status_allowed or requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_CANONICAL_SURFACE_CONTRACT,
        "surface_id": surface_id,
        "surface_name": RECOVERY_CANONICAL_SURFACE_NAME if surface_allowed else None,
        "requested_surface": requested_surface,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "canonical_surface": True,
        "single_canonical_surface": True,
        "only_public_runtime_recovery_entry_surface": True,
        "public_entry_api": "prepare_canonical_runtime_recovery_surface",
        "competing_public_runtime_recovery_surfaces": [],
        "competing_entry_points_allowed": False,
        "future_recovery_entry_must_flow_through_surface": True,
        "future_packages_must_enter_through_surface": True,
        "future_public_entry_api_allowed": False,
        "future_connectors_require_go_review": True,
        "owns_public_runtime_recovery_interface_only": True,
        "owns_recovery_policy": False,
        "owns_recovery_planning": False,
        "owns_recovery_scheduling": False,
        "owns_recovery_execution": False,
        "owns_recovery_supervision": False,
        "owns_recovery_state_machine": False,
        "owns_recovery_persistence": False,
        "owns_recovery_audit": False,
        "owns_recovery_journaling": False,
        "owns_recovery_hook_registration": False,
        "owns_recovery_binding": False,
        "owns_recovery_endpoint_invocation": False,
        "may_validate_normalize_forward_after_go": True,
        "stable_compatibility_boundary": True,
        "public_api_stable": True,
        "ownership_boundary_stable": True,
        "requires_major_version_for_breaking_public_api": True,
        "silent_replacement_allowed": False,
        "bypass_allowed": False,
        "silent_deprecation_allowed": False,
        "all_callers_must_remain_compatible": True,
        "surface_enabled": False,
        "surface_wired_into_runtime": False,
        "runtime_wiring_enabled": False,
        "runtime_supervisor_bridge_changed": False,
        "runtime_hook_registered": False,
        "runtime_binding_applied": False,
        "endpoint_invoked": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "activation_allowed": False,
        "execution_allowed": False,
        "scheduler_called": False,
        "taskrunner_called": False,
        "operator_called": False,
        "dispatcher_called": False,
        "supervisor_called": False,
        "native_runtime_called": False,
        "watchdog_called": False,
        "runtime_state_mutated": False,
        "persistence_called": False,
        "audit_called": False,
        "journal_called": False,
        "subprocess_called": False,
        "filesystem_mutation_called": False,
        "denied_capabilities": list(RECOVERY_CANONICAL_SURFACE_DENIED_CAPABILITIES),
        "reason": _reason(
            requested_surface=requested_surface,
            requested_status=requested_status,
            surface_allowed=surface_allowed,
            status_allowed=status_allowed,
            denied=denied,
        ),
        "metadata": _plain_mapping(metadata),
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _reason(
    *,
    requested_surface: str,
    requested_status: str,
    surface_allowed: bool,
    status_allowed: bool,
    denied: bool,
) -> str | None:
    if denied:
        return "activation or execution attempts are denied while canonical Runtime Recovery surface remains disabled"
    if not surface_allowed:
        return f"canonical Runtime Recovery surface must be {RECOVERY_CANONICAL_SURFACE_NAME}: {requested_surface}"
    if not status_allowed:
        return f"unsupported canonical Runtime Recovery surface status: {requested_status}"
    if requested_status == "blocked":
        return "caller requested passive blocked canonical surface status"
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
