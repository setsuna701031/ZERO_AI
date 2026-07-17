from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_governed_capability_runtime_validation import CLAIMS, SCHEMA_VERSION, STAGES, fingerprint

CLOSURE_CONTRACT = "zero.runtime.governed_capability_runtime_closure.v1"


def close_governed_capability_runtime(runtime_input: Mapping[str, Any], state: Mapping[str, Any],
                                      stage_results: Mapping[str, Any], artifacts: Mapping[str, Any]) -> dict[str, Any]:
    states = state.get("stage_states", {})
    handoff = artifacts.get("prepared_transaction_handoff", {})
    integration = artifacts.get("transaction_integration_closure", {})
    required = all(states.get(name, {}).get("status") in {"completed", "skipped"} for name in STAGES[:-1])
    stage_checks = {"required_stages_closed": required, "order_fixed": state.get("stage_order") == list(STAGES)}
    lineage_checks = {"references_present": all(
        isinstance(v, Mapping) and bool(v.get("artifact_id")) and bool(v.get("artifact_fingerprint"))
        for v in state.get("artifact_references", {}).values())}
    scope_checks = {"effective_scope_contained": state.get("effective_scope") == state.get("authorized_scope")}
    expected_target = runtime_input.get("explicit_inputs", {}).get("execution_intent", {}).get("target_descriptor", {})
    target_checks = {"target_preserved": handoff.get("target_boundary") == state.get("target_boundary") == expected_target}
    limitation_checks = {"limitations_preserved": handoff.get("limitations") == state.get("limitations")}
    permission_checks = {"all_permissions_false": all(v is False for v in state.get("permissions", {}).values())}
    claim_checks = {"all_claims_false": all(state.get(k) is False for k in CLAIMS)}
    side_effect_checks = {
        "dry_run_only": state.get("dry_run_only") is True,
        "handoff_zero_effects": handoff.get("expected_effects") == [],
        "transaction_not_committed": handoff.get("transaction_committed_claim") is False,
    }
    ok = (required and all(stage_checks.values()) and all(lineage_checks.values()) and all(scope_checks.values())
          and all(target_checks.values()) and all(limitation_checks.values()) and all(permission_checks.values())
          and all(claim_checks.values()) and all(side_effect_checks.values())
          and handoff.get("handoff_status") == "prepared"
          and integration.get("verification_status") == "verified_closed")
    body = {
        "contract": CLOSURE_CONTRACT, "schema_version": SCHEMA_VERSION,
        "runtime_id": state.get("runtime_id", ""), "runtime_fingerprint": state.get("runtime_fingerprint", ""),
        "input_id": state.get("input_id", ""), "input_fingerprint": state.get("input_fingerprint", ""),
        "stage_closure_references": deepcopy(state.get("artifact_references", {})),
        "prepared_transaction_handoff_id": handoff.get("handoff_id", ""),
        "prepared_transaction_handoff_fingerprint": handoff.get("handoff_fingerprint", ""),
        "transaction_integration_closure_id": integration.get("integration_closure_id", ""),
        "transaction_integration_closure_fingerprint": integration.get("integration_closure_fingerprint", ""),
        "stage_consistency_results": stage_checks, "lineage_consistency_results": lineage_checks,
        "scope_consistency_results": scope_checks, "target_consistency_results": target_checks,
        "limitation_preservation_results": limitation_checks, "permission_invariant_results": permission_checks,
        "claim_invariant_results": claim_checks, "side_effect_invariant_results": side_effect_checks,
        "verification_status": "verified_closed" if ok else "blocked", "closed": ok,
        "prepared_transaction_available": ok,
        **{name: False for name in CLAIMS},
        "reasons": ["governed_capability_runtime_verified_closed" if ok else "governed_capability_runtime_blocked"],
        "blocked_reasons": [] if ok else ["runtime_closure_invariant_failed"], "failure_reasons": [],
    }
    value = fingerprint(body)
    return {**body, "runtime_closure_id": "governed-capability-runtime-closure-" + value[:24], "runtime_closure_fingerprint": value}
