from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_integration_configuration_validation import validate_runtime_integration_configuration
from core.runtime.runtime_capability_strategy_runtime_integration_decision_validation import validate_runtime_integration_decision
from core.runtime.runtime_capability_strategy_runtime_integration_wiring_validation import validate_runtime_integration_wiring

SCHEMA = "zero.runtime.capability_strategy_runtime_integration_verification.v1"
STATUSES = frozenset({"verified", "not_verified", "rejected", "invalid"})

def verify_runtime_integration(configuration: Any, decision: Any, wiring: Any) -> dict[str, Any]:
    cv = validate_runtime_integration_configuration(configuration).valid
    dv = validate_runtime_integration_decision(decision, configuration).valid
    wv = validate_runtime_integration_wiring(wiring, decision).valid
    linkage_valid = bool(dv and wv)
    status_monotonic = bool(linkage_valid)
    payload_monotonic = bool(linkage_valid and (wiring.get("status") != "wired" or wiring.get("wiring_payload") == decision.get("decision_payload") == configuration.get("configuration_payload")))
    boundary_safe = bool(cv and dv and wv)
    evidence = {"configuration_valid": cv, "decision_valid": dv, "wiring_valid": wv,
                "linkage_valid": linkage_valid, "status_monotonic": status_monotonic,
                "payload_monotonic": payload_monotonic, "boundary_safe": boundary_safe,
                "runtime_activation_absent": boundary_safe, "authority_absent": boundary_safe}
    source_status = wiring.get("status") if isinstance(wiring, Mapping) else None
    if not all(evidence.values()): status = "invalid"
    elif source_status == "wired": status = "verified"
    elif source_status == "rejected": status = "rejected"
    elif source_status == "default_compatible": status = "not_verified"
    else: status = "invalid"
    value = wiring if isinstance(wiring, Mapping) else {}
    links = {k: value.get(k) for k in value if k.startswith("source_")}
    payload = deepcopy(value.get("wiring_payload")) if status == "verified" else None
    base = {"schema": SCHEMA, "status": status,
            "source_configuration_id": configuration.get("configuration_id") if isinstance(configuration, Mapping) else None,
            "source_configuration_fingerprint": configuration.get("fingerprint") if isinstance(configuration, Mapping) else None,
            "source_decision_id": decision.get("decision_id") if isinstance(decision, Mapping) else None,
            "source_decision_fingerprint": decision.get("fingerprint") if isinstance(decision, Mapping) else None,
            "source_integration_wiring_id": value.get("wiring_id"),
            "source_integration_wiring_fingerprint": value.get("fingerprint"), **links,
            "verification_payload": payload, "evidence": evidence,
            "reasons": [{"verified": "runtime_integration_chain_verified", "not_verified": "compatible_chain_not_promoted", "rejected": "rejected_chain_not_promoted", "invalid": "runtime_integration_chain_invalid"}[status]],
            "boundary": {"sealed": True, "read_only": True, "passive_verification": True,
                         "runtime_activation": False, "scope_expansion": False, "constraint_weakening": False,
                         "authority_granted": False, "live_binding": False}}
    return _identified(base, "verification_id", "capability-strategy-runtime-integration-verification-")

build_runtime_integration_verification = verify_runtime_integration
__all__ = ["SCHEMA", "STATUSES", "build_runtime_integration_verification", "verify_runtime_integration"]
