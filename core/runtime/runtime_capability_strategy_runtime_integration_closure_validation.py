from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_integration_decision_validation import _unsafe
from core.runtime.runtime_capability_strategy_runtime_integration_verification_validation import validate_runtime_integration_verification
from core.runtime.runtime_capability_strategy_runtime_integration_closure import SCHEMA, STATUSES

@dataclass(frozen=True)
class RuntimeIntegrationClosureValidationResult:
    valid: bool
    errors: tuple[str, ...]

_LINKS = ("source_configuration_id", "source_configuration_fingerprint", "source_decision_id", "source_decision_fingerprint", "source_integration_wiring_id", "source_integration_wiring_fingerprint", "source_integration_consumer_id", "source_integration_consumer_fingerprint", "source_integration_boundary_id", "source_integration_boundary_fingerprint", "source_consumption_id", "source_consumption_fingerprint", "source_wiring_id", "source_wiring_fingerprint", "source_bootstrap_configuration_id", "source_bootstrap_configuration_fingerprint", "source_runtime_decision_id", "source_strategy_id", "source_profile_id")
_REQUIRED = {"schema", "closure_id", "fingerprint", "status", "source_verification_id", "source_verification_fingerprint", *_LINKS, "closure_payload", "reasons", "boundary"}
_PAYLOAD = {"final_wiring_id", "final_wiring_fingerprint", "passive_integration_payload", "closure_evidence"}

def _expected_boundary(status: Any) -> dict[str, bool]:
    return {"sealed": True, "read_only": True, "verification_closed": status == "closed", "passive_closure": True,
            "runtime_activation": False, "execution_started": False, "authority_granted": False,
            "scope_expansion": False, "constraint_weakening": False, "live_binding": False}

def _identity_valid(value: Mapping[str, Any]) -> bool:
    expected = _identified({k: v for k, v in value.items() if k not in {"closure_id", "fingerprint"}}, "closure_id", "capability-strategy-runtime-integration-closure-")
    return value.get("closure_id") == expected["closure_id"] and value.get("fingerprint") == expected["fingerprint"]

def _boundary_valid(value: Mapping[str, Any]) -> bool: return value.get("boundary") == _expected_boundary(value.get("status"))

def _monotonic(value: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    if value.get("source_verification_id") != source.get("verification_id") or value.get("source_verification_fingerprint") != source.get("fingerprint"): return False
    if any(value.get(k) != source.get(k) for k in _LINKS): return False
    status = {"verified": "closed", "not_verified": "not_closed", "rejected": "rejected", "invalid": "invalid"}.get(source.get("status"))
    if value.get("status") != status: return False
    if status != "closed": return value.get("closure_payload") is None
    return value.get("closure_payload") == {"final_wiring_id": source.get("source_integration_wiring_id"), "final_wiring_fingerprint": source.get("source_integration_wiring_fingerprint"), "passive_integration_payload": source.get("verification_payload"), "closure_evidence": source.get("evidence")}

def validate_runtime_integration_closure(value: Any, source_verification: Any = None) -> RuntimeIntegrationClosureValidationResult:
    if not isinstance(value, Mapping): return RuntimeIntegrationClosureValidationResult(False, ("closure_not_object",))
    errors = [f"missing:{k}" for k in sorted(_REQUIRED - set(value))] + [f"unexpected:{k}" for k in sorted(set(value) - _REQUIRED)]
    if value.get("schema") != SCHEMA or value.get("status") not in STATUSES: errors.append("invalid_contract")
    payload = value.get("closure_payload")
    if value.get("status") == "closed":
        if not isinstance(payload, Mapping) or set(payload) != _PAYLOAD or not all(payload.get("closure_evidence", {}).values()): errors.append("invalid_closure_payload")
    elif payload is not None: errors.append("unsafe_closure_payload")
    if not _boundary_valid(value) or _unsafe(value): errors.append("unsafe_boundary")
    try: valid_id = _identity_valid(value)
    except (TypeError, ValueError): valid_id = False
    if not valid_id: errors.append("identity_mismatch")
    if source_verification is not None:
        if not isinstance(source_verification, Mapping) or not validate_runtime_integration_verification(source_verification).valid: errors.append("invalid_source_verification")
        elif not _monotonic(value, source_verification): errors.append("source_verification_mismatch")
    return RuntimeIntegrationClosureValidationResult(not errors, tuple(dict.fromkeys(errors)))

__all__ = ["RuntimeIntegrationClosureValidationResult", "validate_runtime_integration_closure"]
