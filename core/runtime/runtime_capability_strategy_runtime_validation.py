from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import SCHEMA as CONSUMER_SCHEMA, STATUSES as CONSUMER_STATUSES, _identified
from core.runtime.runtime_capability_strategy_runtime_integration import SCHEMA as INTEGRATION_SCHEMA, STATUSES as INTEGRATION_STATUSES
from core.runtime.runtime_capability_strategy_runtime_decision import SCHEMA as DECISION_SCHEMA, STATUSES as DECISION_STATUSES


@dataclass(frozen=True)
class RuntimeStrategyValidationResult:
    valid: bool
    errors: tuple[str, ...]


def _identity_valid(value: Mapping[str, Any], key: str, prefix: str) -> bool:
    base = {name: item for name, item in value.items() if name not in {key, "fingerprint"}}
    expected = _identified(dict(base), key, prefix)
    return value.get(key) == expected[key] and value.get("fingerprint") == expected["fingerprint"]


def _directives_valid(value: Any) -> bool:
    if value is None:
        return True
    required = {"execution_mode", "worker_limit", "network_mode", "resource_mode", "accelerator_mode", "available_tools", "fallback_applied", "source_strategy_id", "source_strategy_fingerprint"}
    if not isinstance(value, Mapping) or set(value) != required:
        return False
    workers, tools = value.get("worker_limit"), value.get("available_tools")
    return (isinstance(workers, int) and not isinstance(workers, bool) and workers >= 1
            and isinstance(tools, list) and tools == sorted(set(tools), key=str.casefold)
            and all(isinstance(item, str) and item for item in tools))


def validate_consumer_result(value: Any) -> RuntimeStrategyValidationResult:
    errors: list[str] = []
    if not isinstance(value, Mapping): return RuntimeStrategyValidationResult(False, ("consumer_not_object",))
    if value.get("schema") != CONSUMER_SCHEMA or value.get("status") not in CONSUMER_STATUSES: errors.append("invalid_contract")
    if not _directives_valid(value.get("runtime_directives")): errors.append("invalid_runtime_directives")
    if value.get("status") in {"invalid", "default_compatible"} and value.get("runtime_directives") is not None: errors.append("unsafe_directives")
    if value.get("boundary") != {"read_only": True, "execution_authority": False, "mutation_authority": False}: errors.append("unsafe_boundary")
    if not _identity_valid(value, "consumer_id", "capability-strategy-consumer-"): errors.append("identity_mismatch")
    return RuntimeStrategyValidationResult(not errors, tuple(errors))


def validate_integration_result(value: Any) -> RuntimeStrategyValidationResult:
    errors: list[str] = []
    if not isinstance(value, Mapping): return RuntimeStrategyValidationResult(False, ("integration_not_object",))
    if value.get("schema") != INTEGRATION_SCHEMA or value.get("status") not in INTEGRATION_STATUSES: errors.append("invalid_contract")
    if not _directives_valid(value.get("runtime_directives")): errors.append("invalid_runtime_directives")
    if value.get("decision_input_only") is not True or value.get("executor_ownership_changed") is not False: errors.append("unsafe_boundary")
    if not _identity_valid(value, "integration_id", "capability-strategy-integration-"): errors.append("identity_mismatch")
    return RuntimeStrategyValidationResult(not errors, tuple(errors))


def validate_decision_record(value: Any) -> RuntimeStrategyValidationResult:
    errors: list[str] = []
    if not isinstance(value, Mapping): return RuntimeStrategyValidationResult(False, ("decision_not_object",))
    if value.get("schema") != DECISION_SCHEMA or value.get("status") not in DECISION_STATUSES: errors.append("invalid_contract")
    if value.get("decision_input_only") is not True or value.get("authority_granted") is not False: errors.append("unsafe_boundary")
    if not _identity_valid(value, "decision_id", "capability-strategy-decision-"): errors.append("identity_mismatch")
    return RuntimeStrategyValidationResult(not errors, tuple(errors))


__all__ = ["RuntimeStrategyValidationResult", "validate_consumer_result", "validate_integration_result", "validate_decision_record"]
