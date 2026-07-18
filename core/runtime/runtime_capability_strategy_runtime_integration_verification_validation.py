from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_integration_decision_validation import _unsafe, validate_runtime_integration_decision
from core.runtime.runtime_capability_strategy_runtime_integration_configuration_validation import validate_runtime_integration_configuration
from core.runtime.runtime_capability_strategy_runtime_integration_wiring_validation import validate_runtime_integration_wiring
from core.runtime.runtime_capability_strategy_runtime_integration_verification import SCHEMA, STATUSES

@dataclass(frozen=True)
class RuntimeIntegrationVerificationValidationResult:
    valid: bool
    errors: tuple[str, ...]

_UPSTREAM = ("source_integration_consumer_id", "source_integration_consumer_fingerprint", "source_integration_boundary_id", "source_integration_boundary_fingerprint", "source_consumption_id", "source_consumption_fingerprint", "source_wiring_id", "source_wiring_fingerprint", "source_bootstrap_configuration_id", "source_bootstrap_configuration_fingerprint", "source_runtime_decision_id", "source_strategy_id", "source_profile_id")
_REQUIRED = {"schema", "verification_id", "fingerprint", "status", "source_configuration_id", "source_configuration_fingerprint", "source_decision_id", "source_decision_fingerprint", "source_integration_wiring_id", "source_integration_wiring_fingerprint", *_UPSTREAM, "verification_payload", "evidence", "reasons", "boundary"}
_EVIDENCE = {"configuration_valid", "decision_valid", "wiring_valid", "linkage_valid", "status_monotonic", "payload_monotonic", "boundary_safe", "runtime_activation_absent", "authority_absent"}
_BOUNDARY = {"sealed": True, "read_only": True, "passive_verification": True, "runtime_activation": False, "scope_expansion": False, "constraint_weakening": False, "authority_granted": False, "live_binding": False}

def _identity_valid(value: Mapping[str, Any]) -> bool:
    expected = _identified({k: v for k, v in value.items() if k not in {"verification_id", "fingerprint"}}, "verification_id", "capability-strategy-runtime-integration-verification-")
    return value.get("verification_id") == expected["verification_id"] and value.get("fingerprint") == expected["fingerprint"]

def _boundary_valid(value: Mapping[str, Any]) -> bool: return value.get("boundary") == _BOUNDARY

def _monotonic(value: Mapping[str, Any], configuration: Mapping[str, Any], decision: Mapping[str, Any], wiring: Mapping[str, Any]) -> bool:
    direct = (value.get("source_configuration_id") == configuration.get("configuration_id") and value.get("source_configuration_fingerprint") == configuration.get("fingerprint") and value.get("source_decision_id") == decision.get("decision_id") and value.get("source_decision_fingerprint") == decision.get("fingerprint") and value.get("source_integration_wiring_id") == wiring.get("wiring_id") and value.get("source_integration_wiring_fingerprint") == wiring.get("fingerprint"))
    links = all(value.get(k) == wiring.get(k) for k in _UPSTREAM)
    expected = {"wired": "verified", "default_compatible": "not_verified", "rejected": "rejected", "invalid": "invalid"}.get(wiring.get("status"))
    payload = wiring.get("wiring_payload") if expected == "verified" else None
    return direct and links and value.get("status") == expected and value.get("verification_payload") == payload

def validate_runtime_integration_verification(value: Any, source_configuration: Any = None, source_decision: Any = None, source_wiring: Any = None) -> RuntimeIntegrationVerificationValidationResult:
    if not isinstance(value, Mapping): return RuntimeIntegrationVerificationValidationResult(False, ("verification_not_object",))
    errors = [f"missing:{k}" for k in sorted(_REQUIRED - set(value))] + [f"unexpected:{k}" for k in sorted(set(value) - _REQUIRED)]
    if value.get("schema") != SCHEMA or value.get("status") not in STATUSES: errors.append("invalid_contract")
    evidence = value.get("evidence")
    if not isinstance(evidence, Mapping) or set(evidence) != _EVIDENCE or not all(isinstance(v, bool) for v in evidence.values()): errors.append("invalid_evidence")
    elif value.get("status") == "verified" and not all(evidence.values()): errors.append("unverified_success")
    if value.get("status") == "verified":
        if not isinstance(value.get("verification_payload"), Mapping): errors.append("invalid_verification_payload")
    elif value.get("verification_payload") is not None: errors.append("unsafe_verification_payload")
    if value.get("boundary") != _BOUNDARY or _unsafe(value): errors.append("unsafe_boundary")
    try: valid_id = _identity_valid(value)
    except (TypeError, ValueError): valid_id = False
    if not valid_id: errors.append("identity_mismatch")
    supplied = (source_configuration, source_decision, source_wiring)
    if any(x is not None for x in supplied):
        if not all(isinstance(x, Mapping) for x in supplied): errors.append("incomplete_source_chain")
        elif not validate_runtime_integration_configuration(source_configuration).valid or not validate_runtime_integration_decision(source_decision, source_configuration).valid or not validate_runtime_integration_wiring(source_wiring, source_decision).valid: errors.append("invalid_source_chain")
        elif not _monotonic(value, source_configuration, source_decision, source_wiring): errors.append("source_chain_mismatch")
    return RuntimeIntegrationVerificationValidationResult(not errors, tuple(dict.fromkeys(errors)))

__all__ = ["RuntimeIntegrationVerificationValidationResult", "validate_runtime_integration_verification"]
