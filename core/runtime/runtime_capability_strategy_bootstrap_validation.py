from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_validation import validate_decision_record
from core.runtime.runtime_capability_strategy_bootstrap_consumer import SCHEMA as CONSUMER_SCHEMA, STATUSES as CONSUMER_STATUSES
from core.runtime.runtime_capability_strategy_bootstrap_configuration import SCHEMA as CONFIGURATION_SCHEMA, STATUSES as CONFIGURATION_STATUSES
from core.runtime.runtime_capability_strategy_bootstrap_decision import SCHEMA as DECISION_SCHEMA, STATUSES as DECISION_STATUSES


@dataclass(frozen=True)
class BootstrapStrategyValidationResult:
    valid: bool
    errors: tuple[str, ...]


def _identity_valid(value: Mapping[str, Any], key: str, prefix: str) -> bool:
    base = {name: item for name, item in value.items() if name not in {key, "fingerprint"}}
    expected = _identified(dict(base), key, prefix)
    return value.get(key) == expected[key] and value.get("fingerprint") == expected["fingerprint"]


def _boundary_valid(value: Mapping[str, Any]) -> bool:
    return value.get("decision_input_only") is True and value.get("authority_granted") is False and value.get("executor_ownership_changed") is False


def _fields_valid(fields: Any, *, allow_none: bool = True) -> bool:
    if fields is None: return allow_none
    required = {"bootstrap_mode", "execution_mode", "worker_limit", "network_mode", "resource_mode", "accelerator_mode", "available_tools", "compatibility_mode", "fallback_applied", "source_runtime_decision_id", "source_runtime_decision_fingerprint", "source_strategy_id", "source_strategy_fingerprint"}
    if not isinstance(fields, Mapping) or set(fields) != required: return False
    tools = fields.get("available_tools")
    return isinstance(tools, list) and tools == sorted(set(tools), key=str.casefold) and all(isinstance(item, str) and item for item in tools)


def _monotonic(fields: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    if source.get("status") == "default_compatible":
        return (fields.get("compatibility_mode") is True and fields.get("worker_limit") is None
                and fields.get("execution_mode") is None and fields.get("network_mode") is None
                and fields.get("resource_mode") is None and fields.get("accelerator_mode") is None
                and fields.get("available_tools") == [])
    directives = source.get("accepted_directives")
    if not isinstance(directives, Mapping): return False
    return (fields.get("worker_limit") <= directives.get("worker_limit")
            and set(fields.get("available_tools", [])) <= set(directives.get("available_tools", []))
            and all(fields.get(key) == directives.get(key) for key in ("execution_mode", "network_mode", "resource_mode", "accelerator_mode")))


def validate_bootstrap_consumer(value: Any, source_decision: Any = None) -> BootstrapStrategyValidationResult:
    errors: list[str] = []
    if not isinstance(value, Mapping): return BootstrapStrategyValidationResult(False, ("consumer_not_object",))
    if value.get("schema") != CONSUMER_SCHEMA or value.get("status") not in CONSUMER_STATUSES: errors.append("invalid_contract")
    fields = value.get("configuration_fields")
    if not _fields_valid(fields): errors.append("invalid_configuration_fields")
    if value.get("status") == "rejected" and fields is not None: errors.append("unsafe_rejected_configuration")
    if not _boundary_valid(value): errors.append("unsafe_boundary")
    if not _identity_valid(value, "consumer_id", "capability-strategy-bootstrap-consumer-"): errors.append("identity_mismatch")
    if source_decision is not None:
        if not validate_decision_record(source_decision).valid: errors.append("invalid_source_decision")
        elif fields is not None and not _monotonic(fields, source_decision): errors.append("monotonic_restriction_violation")
        elif value.get("source_runtime_decision_linkage") != {"decision_id": source_decision.get("decision_id"), "fingerprint": source_decision.get("fingerprint")}: errors.append("source_decision_linkage_mismatch")
    return BootstrapStrategyValidationResult(not errors, tuple(errors))


def validate_bootstrap_configuration(value: Any, source_decision: Any = None) -> BootstrapStrategyValidationResult:
    errors: list[str] = []
    if not isinstance(value, Mapping): return BootstrapStrategyValidationResult(False, ("configuration_not_object",))
    if value.get("schema") != CONFIGURATION_SCHEMA or value.get("status") not in CONFIGURATION_STATUSES: errors.append("invalid_contract")
    fields = value.get("configuration")
    if not _fields_valid(fields): errors.append("invalid_configuration")
    if value.get("status") == "rejected" and fields is not None: errors.append("unsafe_rejected_configuration")
    if not _boundary_valid(value): errors.append("unsafe_boundary")
    if not _identity_valid(value, "configuration_id", "capability-strategy-bootstrap-configuration-"): errors.append("identity_mismatch")
    if source_decision is not None and fields is not None and (not validate_decision_record(source_decision).valid or not _monotonic(fields, source_decision)): errors.append("monotonic_restriction_violation")
    return BootstrapStrategyValidationResult(not errors, tuple(errors))


def validate_bootstrap_decision(value: Any, source_decision: Any = None) -> BootstrapStrategyValidationResult:
    errors: list[str] = []
    if not isinstance(value, Mapping): return BootstrapStrategyValidationResult(False, ("decision_not_object",))
    if value.get("schema") != DECISION_SCHEMA or value.get("status") not in DECISION_STATUSES: errors.append("invalid_contract")
    fields = value.get("configuration")
    if not _fields_valid(fields): errors.append("invalid_configuration")
    if not _boundary_valid(value): errors.append("unsafe_boundary")
    if not _identity_valid(value, "decision_id", "capability-strategy-bootstrap-decision-"): errors.append("identity_mismatch")
    if source_decision is not None and fields is not None and (not validate_decision_record(source_decision).valid or not _monotonic(fields, source_decision)): errors.append("monotonic_restriction_violation")
    return BootstrapStrategyValidationResult(not errors, tuple(errors))


__all__ = ["BootstrapStrategyValidationResult", "validate_bootstrap_consumer", "validate_bootstrap_configuration", "validate_bootstrap_decision"]
