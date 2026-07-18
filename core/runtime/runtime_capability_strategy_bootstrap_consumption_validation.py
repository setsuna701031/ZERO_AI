from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_bootstrap_consumption import SCHEMA, STATUSES
from core.runtime.runtime_capability_strategy_bootstrap_wiring_validation import validate_wiring_result


@dataclass(frozen=True)
class BootstrapConsumptionValidationResult:
    valid: bool
    errors: tuple[str, ...]


_REQUIRED = {
    "schema", "consumption_id", "fingerprint", "status", "source_wiring_id",
    "source_wiring_fingerprint", "source_bootstrap_configuration_id",
    "source_bootstrap_configuration_fingerprint", "source_runtime_decision_id",
    "source_strategy_id", "source_profile_id", "consumer_payload", "reasons", "boundary",
}
_PAYLOAD_KEYS = {"target_bootstrap_stage", "effective_bootstrap_options"}
_OPTION_KEYS = {"bootstrap_mode", "execution_mode", "worker_limit", "network_mode", "resource_mode", "accelerator_mode", "available_tools"}
_BOUNDARY = {"read_only": True, "consumer_input_only": True, "runtime_activation": False, "scope_expansion": False}
_FORBIDDEN = {"execution_authority", "mutation_authority", "approval_authority", "authorization_authority", "authority_granted", "executor_ownership_changed", "runtime_started"}


def _identity_valid(value: Mapping[str, Any]) -> bool:
    base = {key: item for key, item in value.items() if key not in {"consumption_id", "fingerprint"}}
    expected = _identified(dict(base), "consumption_id", "capability-strategy-bootstrap-consumption-")
    return value.get("consumption_id") == expected["consumption_id"] and value.get("fingerprint") == expected["fingerprint"]


def _boundary_valid(value: Mapping[str, Any]) -> bool:
    return value.get("boundary") == _BOUNDARY


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(key in _FORBIDDEN or _contains_forbidden(item) for key, item in value.items())
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
    return (payload.get("target_bootstrap_stage") in {"plan", "integration", "consumer"}
            and isinstance(workers, int) and not isinstance(workers, bool) and workers >= 1
            and isinstance(tools, list) and tools == sorted(set(tools), key=str.casefold)
            and all(isinstance(item, str) and item for item in tools))


def _monotonic(value: Mapping[str, Any], wiring: Mapping[str, Any]) -> bool:
    expected_linkage = {
        "source_wiring_id": wiring.get("wiring_id"),
        "source_wiring_fingerprint": wiring.get("fingerprint"),
        "source_bootstrap_configuration_id": wiring.get("source_bootstrap_configuration_id"),
        "source_bootstrap_configuration_fingerprint": wiring.get("source_bootstrap_configuration_fingerprint"),
        "source_runtime_decision_id": wiring.get("source_runtime_decision_id"),
        "source_strategy_id": wiring.get("source_strategy_id"),
        "source_profile_id": wiring.get("source_profile_id"),
    }
    if any(value.get(key) != item for key, item in expected_linkage.items()):
        return False
    if wiring.get("status") == "wired":
        return value.get("status") == "consumed" and value.get("consumer_payload") == {
            "target_bootstrap_stage": wiring.get("target_bootstrap_stage"),
            "effective_bootstrap_options": wiring.get("effective_bootstrap_options"),
        }
    expected = {"disabled": "default_compatible", "default_compatible": "default_compatible", "rejected": "rejected", "invalid": "invalid"}.get(wiring.get("status"))
    return value.get("status") == expected and value.get("consumer_payload") is None


def validate_bootstrap_consumption(value: Any, source_wiring: Any = None) -> BootstrapConsumptionValidationResult:
    if not isinstance(value, Mapping):
        return BootstrapConsumptionValidationResult(False, ("consumption_not_object",))
    errors = [f"missing:{key}" for key in sorted(_REQUIRED - set(value))]
    errors += [f"unexpected:{key}" for key in sorted(set(value) - _REQUIRED)]
    if value.get("schema") != SCHEMA or value.get("status") not in STATUSES:
        errors.append("invalid_contract")
    if not isinstance(value.get("consumption_id"), str) or not value.get("consumption_id", "").strip():
        errors.append("invalid_identity")
    if not isinstance(value.get("reasons"), list) or not value.get("reasons") or not all(isinstance(item, str) and item for item in value.get("reasons", [])):
        errors.append("invalid_reasons")
    payload = value.get("consumer_payload")
    if value.get("status") == "consumed":
        if not _payload_valid(payload): errors.append("invalid_consumer_payload")
    elif payload is not None:
        errors.append("unsafe_consumer_payload")
    if not _boundary_valid(value) or _contains_forbidden(value):
        errors.append("unsafe_boundary")
    try:
        identity_valid = _identity_valid(value)
    except (TypeError, ValueError):
        identity_valid = False
    if not identity_valid:
        errors.append("identity_mismatch")
    if source_wiring is not None:
        if not isinstance(source_wiring, Mapping) or not validate_wiring_result(source_wiring).valid:
            errors.append("invalid_source_wiring")
        elif not _monotonic(value, source_wiring):
            errors.append("source_wiring_mismatch")
    return BootstrapConsumptionValidationResult(not errors, tuple(errors))


__all__ = ["BootstrapConsumptionValidationResult", "validate_bootstrap_consumption"]
