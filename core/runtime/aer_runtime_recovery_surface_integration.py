"""Disabled data integration for canonical Runtime Recovery layers."""

from __future__ import annotations

from importlib import import_module
from typing import Callable


__all__ = [
    "prepare_runtime_recovery_surface_integration",
]


def _canonical_helper(module_suffix: str, helper_suffix: str) -> Callable[..., dict[str, object]]:
    module = import_module(
        f"core.runtime.aer_runtime_recovery_canonical_{module_suffix}"
    )
    helper_name = "_".join(
        [
            "prepare",
            "canonical",
            "runtime",
            "recovery",
            helper_suffix,
        ]
    )
    helper = getattr(module, helper_name)
    if not callable(helper):
        raise TypeError(f"canonical recovery helper is not callable: {module_suffix}")
    return helper


def prepare_runtime_recovery_surface_integration(
    *,
    request_id: str,
    surface_id: str,
    response_id: str,
    recovery_reason: str,
    runtime_identity: dict[str, object] | None = None,
    recovery_mode: str = "observe",
    recovery_context: dict[str, object] | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Prepare disabled data-only Request -> Surface -> Response integration."""

    plain_runtime_identity = _plain_mapping(runtime_identity)
    plain_recovery_context = _plain_mapping(recovery_context)
    plain_metadata = _plain_mapping(metadata)

    request_helper = _canonical_helper("request", "request")
    surface_helper = _canonical_helper("surface", "surface")
    response_helper = _canonical_helper("response", "response")

    request_result = request_helper(
        request_id=request_id,
        surface_id=surface_id,
        runtime_identity=plain_runtime_identity,
        recovery_reason=recovery_reason,
        recovery_mode=recovery_mode,
        recovery_context=plain_recovery_context,
        metadata=plain_metadata,
    )
    surface_result = surface_helper(
        surface_id=surface_id,
        requested_status=request_result["status"],
        metadata={
            "request_id": request_id,
            "integration": "disabled_data_only",
            **plain_metadata,
        },
    )
    response_result = response_helper(
        response_id=response_id,
        request_id=request_id,
        surface_id=surface_id,
        runtime_identity=plain_runtime_identity,
        accepted=False,
        status=surface_result["status"],
        reason=_first_reason(request_result, surface_result),
        diagnostics={
            "request_status": request_result["status"],
            "surface_status": surface_result["status"],
            "integration": "disabled_data_only",
        },
        metadata=plain_metadata,
    )

    return {
        "schema": "aer.runtime.recovery.surface_integration.disabled.v1",
        "request_id": request_id,
        "surface_id": surface_id,
        "response_id": response_id,
        "status": response_result["status"],
        "disabled": True,
        "data_orchestration_only": True,
        "canonical_surface_remains_only_public_runtime_recovery_boundary": True,
        "request_and_response_are_compatibility_artifacts": True,
        "standalone_runtime_recovery_entry_point": False,
        "runtime_caller_wired": False,
        "recovery_enabled": False,
        "execution_allowed": False,
        "runtime_state_mutated": False,
        "recovery_executed": False,
        "hooks_registered": False,
        "binding_applied": False,
        "endpoint_invoked": False,
        "events_emitted": False,
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
        "owns_recovery_policy": False,
        "owns_recovery_planning": False,
        "owns_recovery_scheduling": False,
        "owns_recovery_execution": False,
        "owns_recovery_supervision": False,
        "owns_recovery_state_machine": False,
        "owns_recovery_persistence": False,
        "owns_recovery_audit": False,
        "owns_recovery_journal": False,
        "owns_recovery_binding": False,
        "owns_recovery_endpoint_invocation": False,
        "owns_recovery_hook_registration": False,
        "request_result": request_result,
        "surface_result": surface_result,
        "response_result": response_result,
        "metadata": plain_metadata,
        "plain_dict_only": True,
    }


def _first_reason(*results: dict[str, object]) -> str | None:
    for result in results:
        reason = result.get("reason")
        if isinstance(reason, str):
            return reason
    return None


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
