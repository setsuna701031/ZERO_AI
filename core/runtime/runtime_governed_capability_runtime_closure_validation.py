from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.runtime.runtime_governed_capability_runtime_closure import CLOSURE_CONTRACT
from core.runtime.runtime_governed_capability_runtime_validation import CLAIMS, SCHEMA_VERSION, fingerprint


@dataclass(frozen=True)
class GovernedCapabilityRuntimeClosureValidationResult:
    valid: bool
    errors: tuple[str, ...]


def validate_governed_capability_runtime_closure(value: Any) -> GovernedCapabilityRuntimeClosureValidationResult:
    if not isinstance(value, Mapping):
        return GovernedCapabilityRuntimeClosureValidationResult(False, ("closure_not_object",))
    errors: list[str] = []
    status = value.get("verification_status")
    if value.get("contract") != CLOSURE_CONTRACT or value.get("schema_version") != SCHEMA_VERSION or status not in {"verified_closed", "blocked", "failed", "invalid"}:
        errors.append("invalid_closure_contract_or_status")
    if value.get("closed") is not (status == "verified_closed") or value.get("prepared_transaction_available") is not (status == "verified_closed"):
        errors.append("invalid_closure_transition")
    checks = ("stage_consistency_results", "lineage_consistency_results", "scope_consistency_results",
              "target_consistency_results", "limitation_preservation_results", "permission_invariant_results",
              "claim_invariant_results", "side_effect_invariant_results")
    if status == "verified_closed" and any(not isinstance(value.get(k), Mapping) or not all(v is True for v in value[k].values()) for k in checks):
        errors.append("success_invariant_failure")
    if any(value.get(k) is not False for k in CLAIMS):
        errors.append("forbidden_claim")
    expected = fingerprint({k: v for k, v in value.items() if k not in {"runtime_closure_id", "runtime_closure_fingerprint"}})
    if value.get("runtime_closure_fingerprint") != expected or value.get("runtime_closure_id") != "governed-capability-runtime-closure-" + expected[:24]:
        errors.append("closure_identity_mismatch")
    return GovernedCapabilityRuntimeClosureValidationResult(not errors, tuple(dict.fromkeys(errors)))

