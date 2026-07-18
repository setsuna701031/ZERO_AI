from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_integration_consumer_validation import validate_runtime_integration_consumer
from core.runtime.runtime_capability_strategy_runtime_integration_configuration import SCHEMA, STATUSES


@dataclass(frozen=True)
class RuntimeIntegrationConfigurationValidationResult:
    valid: bool
    errors: tuple[str, ...]


_REQUIRED = {
    "schema", "configuration_id", "fingerprint", "status", "source_integration_consumer_id",
    "source_integration_consumer_fingerprint", "source_integration_boundary_id",
    "source_integration_boundary_fingerprint", "source_consumption_id", "source_consumption_fingerprint",
    "source_wiring_id", "source_wiring_fingerprint", "source_bootstrap_configuration_id",
    "source_bootstrap_configuration_fingerprint", "source_runtime_decision_id", "source_strategy_id",
    "source_profile_id", "configuration_payload", "reasons", "boundary",
}
_PAYLOAD_KEYS = {"target_bootstrap_stage", "effective_bootstrap_options"}
_OPTION_KEYS = {"bootstrap_mode", "execution_mode", "worker_limit", "network_mode", "resource_mode", "accelerator_mode", "available_tools"}
_BOUNDARY = {"sealed": True, "read_only": True, "passive_configuration": True, "runtime_activation": False, "scope_expansion": False, "constraint_weakening": False}
_FORBIDDEN_KEYS = {
    "runtime_component", "runtime_target", "executor", "executor_target", "scheduler", "scheduler_queue",
    "planner", "planner_command", "mission", "mission_id", "agent", "agent_id", "approval",
    "approval_record", "authorization", "authorization_token", "mutation", "mutation_plan", "callback",
    "handler", "adapter", "provider", "plugin", "import_path", "command", "shell_command",
    "filesystem_path", "environment_probe", "activation_flag", "activation_token", "runtime_handle",
    "execution_authority", "mutation_authority", "approval_authority", "authorization_authority",
}
_UNSAFE_MARKERS = ("/", "\\", ":", "\n", "\r", ";", "|", "&&", "$(", "`")


def _identity_valid(value: Mapping[str, Any]) -> bool:
    base = {key: item for key, item in value.items() if key not in {"configuration_id", "fingerprint"}}
    expected = _identified(dict(base), "configuration_id", "capability-strategy-runtime-integration-configuration-")
    return value.get("configuration_id") == expected["configuration_id"] and value.get("fingerprint") == expected["fingerprint"]


def _boundary_valid(value: Mapping[str, Any]) -> bool:
    return value.get("boundary") == _BOUNDARY


def _contains_forbidden(value: Any) -> bool:
    if callable(value):
        return True
    if isinstance(value, Mapping):
        return any(key in _FORBIDDEN_KEYS or _contains_forbidden(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return not (value is None or isinstance(value, (str, bool, int)))


def _payload_valid(payload: Any) -> bool:
    if not isinstance(payload, Mapping) or set(payload) != _PAYLOAD_KEYS:
        return False
    options = payload.get("effective_bootstrap_options")
    if not isinstance(options, Mapping) or set(options) != _OPTION_KEYS:
        return False
    workers, tools = options.get("worker_limit"), options.get("available_tools")
    strings = [item for item in options.values() if isinstance(item, str)]
    unsafe = any(any(marker in item for marker in _UNSAFE_MARKERS) for item in strings)
    unsafe_tools = any(any(marker in item for marker in _UNSAFE_MARKERS) for item in tools) if isinstance(tools, list) else True
    return (not unsafe and not unsafe_tools
            and payload.get("target_bootstrap_stage") in {"plan", "integration", "consumer"}
            and isinstance(workers, int) and not isinstance(workers, bool) and workers >= 1
            and isinstance(tools, list) and tools == sorted(set(tools), key=str.casefold)
            and all(isinstance(item, str) and item for item in tools))


def _monotonic(value: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    linkage = {
        "source_integration_consumer_id": "consumer_id", "source_integration_consumer_fingerprint": "fingerprint",
        "source_integration_boundary_id": "source_integration_boundary_id", "source_integration_boundary_fingerprint": "source_integration_boundary_fingerprint",
        "source_consumption_id": "source_consumption_id", "source_consumption_fingerprint": "source_consumption_fingerprint",
        "source_wiring_id": "source_wiring_id", "source_wiring_fingerprint": "source_wiring_fingerprint",
        "source_bootstrap_configuration_id": "source_bootstrap_configuration_id", "source_bootstrap_configuration_fingerprint": "source_bootstrap_configuration_fingerprint",
        "source_runtime_decision_id": "source_runtime_decision_id", "source_strategy_id": "source_strategy_id", "source_profile_id": "source_profile_id",
    }
    if any(value.get(target) != source.get(origin) for target, origin in linkage.items()):
        return False
    expected = {"consumed": "configured", "default_compatible": "default_compatible", "rejected": "rejected", "invalid": "invalid"}.get(source.get("status"))
    expected_payload = source.get("consumer_payload") if expected == "configured" else None
    return value.get("status") == expected and value.get("configuration_payload") == expected_payload


def validate_runtime_integration_configuration(value: Any, source_consumer: Any = None) -> RuntimeIntegrationConfigurationValidationResult:
    if not isinstance(value, Mapping):
        return RuntimeIntegrationConfigurationValidationResult(False, ("configuration_not_object",))
    errors = [f"missing:{key}" for key in sorted(_REQUIRED - set(value))]
    errors += [f"unexpected:{key}" for key in sorted(set(value) - _REQUIRED)]
    if value.get("schema") != SCHEMA or value.get("status") not in STATUSES:
        errors.append("invalid_contract")
    if not isinstance(value.get("configuration_id"), str) or not value.get("configuration_id", "").strip():
        errors.append("invalid_identity")
    if not isinstance(value.get("reasons"), list) or not value.get("reasons") or not all(isinstance(item, str) and item for item in value.get("reasons", [])):
        errors.append("invalid_reasons")
    payload = value.get("configuration_payload")
    if value.get("status") == "configured":
        if not _payload_valid(payload): errors.append("invalid_configuration_payload")
    elif payload is not None:
        errors.append("unsafe_configuration_payload")
    if not _boundary_valid(value) or _contains_forbidden(value):
        errors.append("unsafe_boundary")
    try:
        identity_valid = _identity_valid(value)
    except (TypeError, ValueError):
        identity_valid = False
    if not identity_valid:
        errors.append("identity_mismatch")
    if source_consumer is not None:
        if not isinstance(source_consumer, Mapping) or not validate_runtime_integration_consumer(source_consumer).valid:
            errors.append("invalid_source_consumer")
        elif not _monotonic(value, source_consumer):
            errors.append("source_consumer_mismatch")
    return RuntimeIntegrationConfigurationValidationResult(not errors, tuple(errors))


__all__ = ["RuntimeIntegrationConfigurationValidationResult", "validate_runtime_integration_configuration"]
