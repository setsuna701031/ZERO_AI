from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_bootstrap_validation import validate_bootstrap_configuration
from core.runtime.runtime_capability_strategy_bootstrap_wiring import REQUEST_SCHEMA, RESULT_SCHEMA, STATUSES, TARGET_STAGES


@dataclass(frozen=True)
class BootstrapWiringValidationResult:
    valid: bool
    errors: tuple[str, ...]


def _identity_valid(value: Mapping[str, Any], key: str, prefix: str) -> bool:
    base = {name: item for name, item in value.items() if name not in {key, "fingerprint"}}
    expected = _identified(dict(base), key, prefix)
    return value.get(key) == expected[key] and value.get("fingerprint") == expected["fingerprint"]


def validate_wiring_request(value: Any) -> BootstrapWiringValidationResult:
    if not isinstance(value, Mapping): return BootstrapWiringValidationResult(False, ("request_not_object",))
    required = {"schema", "request_id", "enabled", "bootstrap_configuration", "target_bootstrap_stage", "compatibility_mode", "fingerprint"}
    errors = [f"missing:{key}" for key in sorted(required - set(value))] + [f"unexpected:{key}" for key in sorted(set(value) - required)]
    if value.get("schema") != REQUEST_SCHEMA: errors.append("invalid_schema")
    if not isinstance(value.get("enabled"), bool) or not isinstance(value.get("compatibility_mode"), bool): errors.append("invalid_flags")
    if value.get("target_bootstrap_stage") not in TARGET_STAGES: errors.append("unsupported_target_stage")
    configuration = value.get("bootstrap_configuration")
    if configuration is not None and not isinstance(configuration, Mapping): errors.append("invalid_bootstrap_configuration_type")
    if not _identity_valid(value, "request_id", "capability-strategy-bootstrap-wiring-request-"): errors.append("identity_mismatch")
    return BootstrapWiringValidationResult(not errors, tuple(errors))


def _monotonic(options: Mapping[str, Any], configuration: Mapping[str, Any]) -> bool:
    fields = configuration.get("configuration")
    if not isinstance(fields, Mapping): return False
    return (options.get("worker_limit") <= fields.get("worker_limit")
            and set(options.get("available_tools", [])) <= set(fields.get("available_tools", []))
            and all(options.get(key) == fields.get(key) for key in ("execution_mode", "network_mode", "resource_mode", "accelerator_mode")))


def validate_wiring_result(value: Any, source_configuration: Any = None) -> BootstrapWiringValidationResult:
    if not isinstance(value, Mapping): return BootstrapWiringValidationResult(False, ("result_not_object",))
    required = {"schema", "wiring_id", "fingerprint", "status", "enabled", "target_bootstrap_stage", "configuration_applied", "effective_bootstrap_options", "source_bootstrap_configuration_id", "source_bootstrap_configuration_fingerprint", "source_runtime_decision_id", "source_strategy_id", "source_profile_id", "compatibility_mode", "reasons", "decision_input_only", "authority_granted", "executor_ownership_changed", "runtime_started"}
    errors = [f"missing:{key}" for key in sorted(required - set(value))] + [f"unexpected:{key}" for key in sorted(set(value) - required)]
    if value.get("schema") != RESULT_SCHEMA or value.get("status") not in STATUSES: errors.append("invalid_contract")
    if value.get("target_bootstrap_stage") not in TARGET_STAGES and value.get("status") != "invalid": errors.append("unsupported_target_stage")
    options = value.get("effective_bootstrap_options")
    if value.get("configuration_applied") is True:
        option_keys = {"bootstrap_mode", "execution_mode", "worker_limit", "network_mode", "resource_mode", "accelerator_mode", "available_tools"}
        if not isinstance(options, Mapping) or set(options) != option_keys: errors.append("invalid_effective_options")
    elif options is not None: errors.append("unexpected_effective_options")
    if value.get("decision_input_only") is not True or value.get("authority_granted") is not False or value.get("executor_ownership_changed") is not False or value.get("runtime_started") is not False: errors.append("unsafe_boundary")
    if not _identity_valid(value, "wiring_id", "capability-strategy-bootstrap-wiring-"): errors.append("identity_mismatch")
    if source_configuration is not None:
        if not validate_bootstrap_configuration(source_configuration).valid: errors.append("invalid_source_configuration")
        elif options is not None and not _monotonic(options, source_configuration): errors.append("monotonic_restriction_violation")
        elif value.get("source_bootstrap_configuration_id") != source_configuration.get("configuration_id") or value.get("source_bootstrap_configuration_fingerprint") != source_configuration.get("fingerprint"): errors.append("source_configuration_linkage_mismatch")
    return BootstrapWiringValidationResult(not errors, tuple(errors))


__all__ = ["BootstrapWiringValidationResult", "validate_wiring_request", "validate_wiring_result"]
