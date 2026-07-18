from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_bootstrap_consumption_validation import validate_bootstrap_consumption
from core.runtime.runtime_capability_strategy_bootstrap_runtime_integration_boundary import SCHEMA, STATUSES


@dataclass(frozen=True)
class BootstrapRuntimeIntegrationBoundaryValidationResult:
    valid: bool
    errors: tuple[str, ...]


_REQUIRED = {
    "schema", "boundary_id", "fingerprint", "status", "source_consumption_id",
    "source_consumption_fingerprint", "source_wiring_id", "source_wiring_fingerprint",
    "source_bootstrap_configuration_id", "source_bootstrap_configuration_fingerprint",
    "source_runtime_decision_id", "source_strategy_id", "source_profile_id",
    "integration_payload", "reasons", "boundary",
}
_PAYLOAD_KEYS = {"target_bootstrap_stage", "effective_bootstrap_options"}
_OPTION_KEYS = {"bootstrap_mode", "execution_mode", "worker_limit", "network_mode", "resource_mode", "accelerator_mode", "available_tools"}
_BOUNDARY = {"sealed": True, "read_only": True, "passive_handoff": True, "runtime_activation": False, "scope_expansion": False}
_FORBIDDEN_KEYS = {
    "executor", "executor_target", "scheduler", "scheduler_queue", "planner", "planner_command",
    "mission", "mission_id", "agent", "agent_id", "approval", "approval_token",
    "authorization", "authorization_token", "mutation", "mutation_plan", "callback",
    "import_path", "executable_command", "shell_command", "filesystem_mutation_instruction",
    "runtime_handle", "execution_authority", "mutation_authority", "approval_authority",
    "authorization_authority", "authority_granted", "runtime_started", "environment_probe",
}


def _identity_valid(value: Mapping[str, Any]) -> bool:
    base = {key: item for key, item in value.items() if key not in {"boundary_id", "fingerprint"}}
    expected = _identified(dict(base), "boundary_id", "capability-strategy-bootstrap-runtime-integration-boundary-")
    return value.get("boundary_id") == expected["boundary_id"] and value.get("fingerprint") == expected["fingerprint"]


def _boundary_valid(value: Mapping[str, Any]) -> bool:
    return value.get("boundary") == _BOUNDARY


def _contains_forbidden(value: Any) -> bool:
    if callable(value):
        return True
    if isinstance(value, Mapping):
        return any(key in _FORBIDDEN_KEYS or _contains_forbidden(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def _payload_valid(payload: Any) -> bool:
    if not isinstance(payload, Mapping) or set(payload) != _PAYLOAD_KEYS:
        return False
    options = payload.get("effective_bootstrap_options")
    if not isinstance(options, Mapping) or set(options) != _OPTION_KEYS:
        return False
    workers, tools = options.get("worker_limit"), options.get("available_tools")
    unsafe_strings = any(any(marker in item for marker in ("/", "\\", ":", "\n", "\r", ";", "|", "&&", "$(", "`"))
                         for item in options.values() if isinstance(item, str))
    unsafe_tools = any(any(marker in item for marker in ("/", "\\", ":", "\n", "\r", ";", "|", "&&", "$(", "`"))
                       for item in tools) if isinstance(tools, list) else True
    return (not unsafe_strings and not unsafe_tools
            and payload.get("target_bootstrap_stage") in {"plan", "integration", "consumer"}
            and isinstance(workers, int) and not isinstance(workers, bool) and workers >= 1
            and isinstance(tools, list) and tools == sorted(set(tools), key=str.casefold)
            and all(isinstance(item, str) and item for item in tools))


def _monotonic(value: Mapping[str, Any], consumption: Mapping[str, Any]) -> bool:
    linkage_keys = {
        "source_consumption_id": "consumption_id",
        "source_consumption_fingerprint": "fingerprint",
        "source_wiring_id": "source_wiring_id",
        "source_wiring_fingerprint": "source_wiring_fingerprint",
        "source_bootstrap_configuration_id": "source_bootstrap_configuration_id",
        "source_bootstrap_configuration_fingerprint": "source_bootstrap_configuration_fingerprint",
        "source_runtime_decision_id": "source_runtime_decision_id",
        "source_strategy_id": "source_strategy_id",
        "source_profile_id": "source_profile_id",
    }
    if any(value.get(target) != consumption.get(source) for target, source in linkage_keys.items()):
        return False
    expected = {"consumed": "integrated", "default_compatible": "default_compatible", "rejected": "rejected", "invalid": "invalid"}.get(consumption.get("status"))
    expected_payload = consumption.get("consumer_payload") if expected == "integrated" else None
    return value.get("status") == expected and value.get("integration_payload") == expected_payload


def validate_bootstrap_runtime_integration_boundary(value: Any, source_consumption: Any = None) -> BootstrapRuntimeIntegrationBoundaryValidationResult:
    if not isinstance(value, Mapping):
        return BootstrapRuntimeIntegrationBoundaryValidationResult(False, ("boundary_not_object",))
    errors = [f"missing:{key}" for key in sorted(_REQUIRED - set(value))]
    errors += [f"unexpected:{key}" for key in sorted(set(value) - _REQUIRED)]
    if value.get("schema") != SCHEMA or value.get("status") not in STATUSES:
        errors.append("invalid_contract")
    if not isinstance(value.get("boundary_id"), str) or not value.get("boundary_id", "").strip():
        errors.append("invalid_identity")
    if not isinstance(value.get("reasons"), list) or not value.get("reasons") or not all(isinstance(item, str) and item for item in value.get("reasons", [])):
        errors.append("invalid_reasons")
    payload = value.get("integration_payload")
    if value.get("status") == "integrated":
        if not _payload_valid(payload): errors.append("invalid_integration_payload")
    elif payload is not None:
        errors.append("unsafe_integration_payload")
    if not _boundary_valid(value) or _contains_forbidden(value):
        errors.append("unsafe_boundary")
    try:
        identity_valid = _identity_valid(value)
    except (TypeError, ValueError):
        identity_valid = False
    if not identity_valid:
        errors.append("identity_mismatch")
    if source_consumption is not None:
        if not isinstance(source_consumption, Mapping) or not validate_bootstrap_consumption(source_consumption).valid:
            errors.append("invalid_source_consumption")
        elif not _monotonic(value, source_consumption):
            errors.append("source_consumption_mismatch")
    return BootstrapRuntimeIntegrationBoundaryValidationResult(not errors, tuple(errors))


__all__ = ["BootstrapRuntimeIntegrationBoundaryValidationResult", "validate_bootstrap_runtime_integration_boundary"]
