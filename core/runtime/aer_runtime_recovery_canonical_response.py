"""Disabled canonical Runtime Recovery response data."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_RECOVERY_CANONICAL_RESPONSE_SCHEMA = "aer.runtime.recovery.canonical_response.v1"
_RECOVERY_CANONICAL_RESPONSE_DENIED_CAPABILITIES = (
    "recovery_execution",
    "recovery_authorization",
    "recovery_scheduling",
    "recovery_dispatch",
    "recovery_mutation",
    "recovery_action",
    "runtime_invocation",
    "canonical_surface_call",
    "canonical_request_helper_call",
    "binding_endpoint_call",
    "activation_gate_call",
    "scheduler_call",
    "taskrunner_call",
    "operator_call",
    "dispatcher_call",
    "supervisor_call",
    "native_runtime_call",
    "watchdog_call",
    "filesystem_mutation",
    "subprocess_call",
    "audit_emission",
    "journal_event",
    "persistence_write",
)

__all__ = [
    "prepare_canonical_runtime_recovery_response",
]


def prepare_canonical_runtime_recovery_response(
    *,
    response_id: str,
    request_id: str,
    surface_id: str,
    runtime_identity: Mapping[str, Any] | None = None,
    accepted: bool = False,
    status: str = "observed",
    reason: str | None = None,
    diagnostics: Mapping[str, Any] | None = None,
    timestamp: str | None = None,
    request_execution: bool = False,
    request_authorization: bool = False,
    request_schedule: bool = False,
    request_dispatch: bool = False,
    request_mutation: bool = False,
    request_recovery: bool = False,
    request_runtime_invocation: bool = False,
    request_surface_call: bool = False,
    request_request_helper_call: bool = False,
    request_binding_endpoint_call: bool = False,
    request_activation_gate_call: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare disabled observation response data without runtime side effects."""

    denied = any(
        (
            request_execution,
            request_authorization,
            request_schedule,
            request_dispatch,
            request_mutation,
            request_recovery,
            request_runtime_invocation,
            request_surface_call,
            request_request_helper_call,
            request_binding_endpoint_call,
            request_activation_gate_call,
        )
    )
    response_status = "denied" if denied else status

    return {
        "schema": _RECOVERY_CANONICAL_RESPONSE_SCHEMA,
        "response_id": response_id,
        "request_id": request_id,
        "surface_id": surface_id,
        "runtime_identity": _plain_mapping(runtime_identity),
        "accepted": bool(accepted) and not denied,
        "execution_allowed": False,
        "recovery_enabled": False,
        "status": response_status,
        "reason": _reason(denied=denied, reason=reason),
        "diagnostics": _plain_mapping(diagnostics),
        "timestamp": timestamp,
        "observation_only": True,
        "disabled": True,
        "prepared": not denied,
        "denied": denied,
        "runtime_state_mutated": False,
        "filesystem_mutation_called": False,
        "subprocess_called": False,
        "audit_called": False,
        "journal_called": False,
        "persistence_called": False,
        "scheduler_called": False,
        "taskrunner_called": False,
        "operator_called": False,
        "dispatcher_called": False,
        "supervisor_called": False,
        "native_runtime_called": False,
        "watchdog_called": False,
        "binding_endpoint_called": False,
        "activation_gate_called": False,
        "canonical_surface_called": False,
        "request_helper_called": False,
        "executes_recovery": False,
        "authorizes_recovery": False,
        "schedules_recovery": False,
        "dispatches_recovery": False,
        "recovers": False,
        "public_compatibility_boundary": True,
        "append_only_public_schema": True,
        "backward_compatible": True,
        "future_fields_must_be_optional": True,
        "major_version_required_for_breaking_schema_change": True,
        "exactly_one_public_response_api": True,
        "public_response_api": "prepare_canonical_runtime_recovery_response",
        "exactly_one_canonical_response_schema": True,
        "competing_public_response_formats_allowed": False,
        "only_public_runtime_recovery_response_object": True,
        "future_packages_must_return_this_shape": True,
        "only_surface_may_publicly_return_response": True,
        "future_implementations_return_through_canonical_surface": True,
        "public_direct_response_exposure_allowed": False,
        "additional_public_response_apis_allowed": False,
        "response_helper_internal_compatibility_artifact": True,
        "standalone_runtime_entry_point": False,
        "response_helper_public_runtime_entry_point": False,
        "canonical_surface_bypass_allowed": False,
        "surface_owns_public_runtime_recovery_entry": True,
        "surface_owns_request_admission": True,
        "surface_owns_request_normalization": True,
        "surface_owns_response_return": True,
        "surface_owns_recovery_execution": False,
        "surface_owns_recovery_planning": False,
        "surface_owns_recovery_scheduling": False,
        "surface_owns_recovery_supervision": False,
        "surface_owns_recovery_state_machine": False,
        "surface_owns_recovery_persistence": False,
        "surface_owns_recovery_audit": False,
        "surface_owns_recovery_journal": False,
        "owns_response_normalization": True,
        "owns_response_validation": True,
        "owns_response_compatibility": True,
        "owns_execution": False,
        "owns_planning": False,
        "owns_scheduling": False,
        "owns_recovery_policy": False,
        "owns_recovery_state": False,
        "owns_runtime_mutation": False,
        "owns_dispatcher": False,
        "owns_operator": False,
        "owns_supervisor": False,
        "owns_watchdog": False,
        "owns_persistence": False,
        "owns_audit": False,
        "owns_journal": False,
        "denied_capabilities": list(_RECOVERY_CANONICAL_RESPONSE_DENIED_CAPABILITIES),
        "metadata": _plain_mapping(metadata),
        "plain_dict_only": True,
    }


def _reason(*, denied: bool, reason: str | None) -> str | None:
    if denied:
        return "execution, authorization, scheduling, dispatch, mutation, recovery, or runtime call denied"
    return reason


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
