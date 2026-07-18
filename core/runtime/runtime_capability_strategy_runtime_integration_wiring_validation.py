from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_integration_decision_validation import _unsafe, validate_runtime_integration_decision
from core.runtime.runtime_capability_strategy_runtime_integration_wiring import SCHEMA, STATUSES

@dataclass(frozen=True)
class RuntimeIntegrationWiringValidationResult:
    valid: bool
    errors: tuple[str, ...]

_UPSTREAM = ("source_configuration_id", "source_configuration_fingerprint", "source_integration_consumer_id", "source_integration_consumer_fingerprint", "source_integration_boundary_id", "source_integration_boundary_fingerprint", "source_consumption_id", "source_consumption_fingerprint", "source_wiring_id", "source_wiring_fingerprint", "source_bootstrap_configuration_id", "source_bootstrap_configuration_fingerprint", "source_runtime_decision_id", "source_strategy_id", "source_profile_id")
_REQUIRED = {"schema", "wiring_id", "fingerprint", "status", "source_decision_id", "source_decision_fingerprint", *_UPSTREAM, "wiring_payload", "reasons", "boundary"}
_BOUNDARY = {"sealed": True, "read_only": True, "passive_wiring": True, "runtime_activation": False, "scope_expansion": False, "constraint_weakening": False, "authority_granted": False, "live_binding": False}

def _identity_valid(value: Mapping[str, Any]) -> bool:
    base = {k: v for k, v in value.items() if k not in {"wiring_id", "fingerprint"}}
    expected = _identified(dict(base), "wiring_id", "capability-strategy-runtime-integration-wiring-")
    return value.get("wiring_id") == expected["wiring_id"] and value.get("fingerprint") == expected["fingerprint"]

def _boundary_valid(value: Mapping[str, Any]) -> bool: return value.get("boundary") == _BOUNDARY

def _monotonic(value: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    if value.get("source_decision_id") != source.get("decision_id") or value.get("source_decision_fingerprint") != source.get("fingerprint"): return False
    if any(value.get(k) != source.get(k) for k in _UPSTREAM): return False
    status = {"decided": "wired", "default_compatible": "default_compatible", "rejected": "rejected", "invalid": "invalid"}.get(source.get("status"))
    return value.get("status") == status and value.get("wiring_payload") == (source.get("decision_payload") if status == "wired" else None)

def validate_runtime_integration_wiring(value: Any, source_decision: Any = None) -> RuntimeIntegrationWiringValidationResult:
    if not isinstance(value, Mapping): return RuntimeIntegrationWiringValidationResult(False, ("wiring_not_object",))
    errors = [f"missing:{k}" for k in sorted(_REQUIRED - set(value))] + [f"unexpected:{k}" for k in sorted(set(value) - _REQUIRED)]
    if value.get("schema") != SCHEMA or value.get("status") not in STATUSES: errors.append("invalid_contract")
    if value.get("status") == "wired":
        if not isinstance(value.get("wiring_payload"), Mapping): errors.append("invalid_wiring_payload")
    elif value.get("wiring_payload") is not None: errors.append("unsafe_wiring_payload")
    if not isinstance(value.get("reasons"), list) or not value.get("reasons"): errors.append("invalid_reasons")
    if not _boundary_valid(value) or _unsafe(value): errors.append("unsafe_boundary")
    try: valid_id = _identity_valid(value)
    except (TypeError, ValueError): valid_id = False
    if not valid_id: errors.append("identity_mismatch")
    if source_decision is not None:
        if not isinstance(source_decision, Mapping) or not validate_runtime_integration_decision(source_decision).valid: errors.append("invalid_source_decision")
        elif not _monotonic(value, source_decision): errors.append("source_decision_mismatch")
    return RuntimeIntegrationWiringValidationResult(not errors, tuple(dict.fromkeys(errors)))

__all__ = ["RuntimeIntegrationWiringValidationResult", "validate_runtime_integration_wiring"]
