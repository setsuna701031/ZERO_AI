"""Disabled Runtime Recovery gateway admission data."""

from __future__ import annotations

from core.runtime.aer_runtime_recovery_surface_integration import (
    prepare_runtime_recovery_surface_integration as _prepare_runtime_recovery_surface_integration,
)


__all__ = [
    "prepare_runtime_recovery_gateway",
]


_ADMISSION_EVALUATION_ORDER = (
    "kill_switch",
    "disabled_gate",
    "future_admission_policy_reserved",
    "future_runtime_authorization_reserved",
    "future_recovery_execution_reserved",
)

_RESERVED_POLICY_RESULT = {
    "enabled": False,
    "policy_status": "reserved",
    "policy_version": "v1_reserved",
    "reason": "future_package",
    "admission_granted": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
}

_RESERVED_AUTHORIZATION_RESULT = {
    "enabled": False,
    "authorization_status": "reserved",
    "authorization_version": "v1_reserved",
    "reason": "future_package",
    "admission_granted": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
}

_RESERVED_RECOVERY_EXECUTION_RESULT = {
    "enabled": False,
    "execution_status": "reserved",
    "execution_version": "v1_reserved",
    "reason": "future_package",
    "admission_granted": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
}


def prepare_runtime_recovery_gateway(
    *,
    request_id: str,
    surface_id: str,
    response_id: str,
    recovery_reason: str,
    runtime_identity: dict[str, object] | None = None,
    recovery_mode: str = "observe",
    recovery_context: dict[str, object] | None = None,
    kill_switch_enabled: bool = True,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Deny Runtime Recovery admission while preserving canonical data flow."""

    plain_metadata = _plain_mapping(metadata)
    gateway_status = "kill_switch_blocked" if kill_switch_enabled else "disabled"
    surface_integration_result = _prepare_runtime_recovery_surface_integration(
        request_id=request_id,
        surface_id=surface_id,
        response_id=response_id,
        recovery_reason=recovery_reason,
        runtime_identity=_plain_mapping(runtime_identity),
        recovery_mode=recovery_mode,
        recovery_context=_plain_mapping(recovery_context),
        metadata={
            "gateway_status": gateway_status,
            "admission_granted": False,
            "kill_switch_enabled": bool(kill_switch_enabled),
            **plain_metadata,
        },
    )

    return {
        "schema": "aer.runtime.recovery.gateway.disabled_admission.v1",
        "request_id": request_id,
        "surface_id": surface_id,
        "response_id": response_id,
        "gateway_status": gateway_status,
        "admission_evaluation_order": list(_ADMISSION_EVALUATION_ORDER),
        "admission_blocking_stage": "kill_switch" if kill_switch_enabled else "disabled_gate",
        "future_packages_must_extend_admission_chain": True,
        "future_packages_may_reorder_admission_chain": False,
        "admission_denied_before_policy": True,
        "kill_switch_enabled": bool(kill_switch_enabled),
        "kill_switch_blocked": bool(kill_switch_enabled),
        "disabled_admission_blocked": not bool(kill_switch_enabled),
        "admission_granted": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "hooks_registered": False,
        "binding_applied": False,
        "endpoint_invoked": False,
        "events_emitted": False,
        "runtime_caller_wired": False,
        "second_execution_path_created": False,
        "canonical_surface_family_bypassed": False,
        "disabled_admission_data_only": True,
        "surface_integration_called_as_data_orchestration_only": True,
        "future_runtime_automation_requires_gateway_go_review": True,
        "scheduler_called": False,
        "taskrunner_called": False,
        "operator_called": False,
        "dispatcher_called": False,
        "supervisor_called": False,
        "native_runtime_called": False,
        "watchdog_called": False,
        "audit_called": False,
        "journal_called": False,
        "persistence_called": False,
        "subprocess_called": False,
        "filesystem_mutation_called": False,
        "owns_admission_denial": True,
        "owns_recovery_policy": False,
        "owns_recovery_planning": False,
        "owns_recovery_scheduling": False,
        "owns_recovery_execution": False,
        "owns_recovery_supervision": False,
        "owns_recovery_state_machine": False,
        "owns_recovery_persistence": False,
        "owns_recovery_audit": False,
        "owns_recovery_journal": False,
        "owns_recovery_hook_registration": False,
        "owns_recovery_binding_application": False,
        "owns_recovery_endpoint_invocation": False,
        "policy_result": dict(_RESERVED_POLICY_RESULT),
        "authorization_result": dict(_RESERVED_AUTHORIZATION_RESULT),
        "recovery_execution_result": dict(_RESERVED_RECOVERY_EXECUTION_RESULT),
        "surface_integration_result": surface_integration_result,
        "metadata": plain_metadata,
        "plain_dict_only": True,
    }


def _plain_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _plain_value(item) for key, item in value.items()}


def _plain_value(value: object) -> object:
    if isinstance(value, dict):
        return _plain_mapping(value)
    if isinstance(value, list):
        return [_plain_value(item) for item in value]
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    return value
