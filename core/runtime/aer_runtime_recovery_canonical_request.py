"""Disabled canonical Runtime Recovery request data."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RECOVERY_CANONICAL_REQUEST_SCHEMA = "aer.runtime.recovery.canonical_request.v1"
RECOVERY_CANONICAL_REQUEST_ALLOWED_MODES = ("observe", "prepare", "dry_run")
RECOVERY_CANONICAL_REQUEST_DENIED_CAPABILITIES = (
    "canonical_surface_call",
    "recovery_execution",
    "recovery_enablement",
    "runtime_hook_registration",
    "runtime_binding_application",
    "endpoint_invocation",
    "runtime_mutation",
    "scheduler_call",
    "taskrunner_call",
    "operator_call",
    "dispatcher_call",
    "supervisor_call",
    "native_runtime_call",
    "watchdog_call",
    "persistence_write",
    "audit_emission",
    "journal_event",
    "subprocess_call",
    "filesystem_mutation",
)

__all__ = [
    "prepare_canonical_runtime_recovery_request",
]


def prepare_canonical_runtime_recovery_request(
    *,
    request_id: str,
    surface_id: str,
    runtime_identity: Mapping[str, Any] | None = None,
    recovery_reason: str,
    recovery_mode: str = "observe",
    recovery_context: Mapping[str, Any] | None = None,
    request_execution: bool = False,
    request_enablement: bool = False,
    request_surface_call: bool = False,
    request_hook_registration: bool = False,
    request_binding_application: bool = False,
    request_endpoint_invocation: bool = False,
    request_runtime_mutation: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare disabled canonical request data without calling Runtime."""

    mode_allowed = recovery_mode in RECOVERY_CANONICAL_REQUEST_ALLOWED_MODES
    denied = any(
        (
            request_execution,
            request_enablement,
            request_surface_call,
            request_hook_registration,
            request_binding_application,
            request_endpoint_invocation,
            request_runtime_mutation,
        )
    )
    prepared = mode_allowed and not denied
    blocked = not mode_allowed and not denied
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "schema": RECOVERY_CANONICAL_REQUEST_SCHEMA,
        "request_id": request_id,
        "surface_id": surface_id,
        "runtime_identity": _plain_mapping(runtime_identity),
        "recovery_reason": recovery_reason,
        "recovery_mode": recovery_mode,
        "recovery_context": _plain_mapping(recovery_context),
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "disabled": True,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "surface_wired": False,
        "owned_by_canonical_surface_family": True,
        "request_helper_connected_to_surface_helper": False,
        "surface_connection_requires_future_go_review": True,
        "canonical_surface_called": False,
        "public_compatibility_boundary": True,
        "append_only_public_schema": True,
        "existing_public_fields_renamable": False,
        "existing_public_fields_removable": False,
        "future_fields_must_be_optional": True,
        "major_version_required_for_breaking_schema_change": True,
        "exactly_one_canonical_request_schema": True,
        "competing_public_request_formats_allowed": False,
        "future_implementations_must_consume_this_request": True,
        "intent_only": True,
        "execution_request": False,
        "runtime_caller_modified": False,
        "runtime_supervisor_bridge_changed": False,
        "hooks_registered": False,
        "binding_applied": False,
        "endpoint_invoked": False,
        "scheduler_called": False,
        "taskrunner_called": False,
        "operator_called": False,
        "dispatcher_called": False,
        "supervisor_called": False,
        "native_runtime_called": False,
        "watchdog_called": False,
        "persistence_called": False,
        "audit_called": False,
        "journal_called": False,
        "subprocess_called": False,
        "filesystem_mutation_called": False,
        "compatible_with_canonical_surface": True,
        "does_not_replace_canonical_surface": True,
        "does_not_bypass_canonical_surface": True,
        "denied_capabilities": list(RECOVERY_CANONICAL_REQUEST_DENIED_CAPABILITIES),
        "reason": _reason(recovery_mode=recovery_mode, mode_allowed=mode_allowed, denied=denied),
        "metadata": _plain_mapping(metadata),
        "plain_dict_only": True,
    }


def _reason(*, recovery_mode: str, mode_allowed: bool, denied: bool) -> str | None:
    if denied:
        return "activation, execution, or runtime wiring attempt denied while canonical request remains disabled"
    if not mode_allowed:
        return f"unsupported canonical Runtime Recovery request mode: {recovery_mode}"
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
