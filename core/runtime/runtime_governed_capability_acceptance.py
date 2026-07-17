from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_governed_capability_runtime import run_governed_capability_runtime
from core.runtime.runtime_governed_capability_runtime_closure_validation import validate_governed_capability_runtime_closure


CONTRACT = "zero.runtime.governed_capability_acceptance.v1"
SCHEMA_VERSION = "1"
RESUME_POINTS = ("decision_readiness_closed", "decision_authorization_closed", "transaction_preparation_input_ready")
STOP_POINTS = ("observation_closed", "decision_authorization_closed", "transaction_prepared", "runtime_closed")
CLAIMS = ("execution_started_claim", "execution_completion_claim", "mutation_authorization_claim",
          "mutation_performed_claim", "transaction_committed_claim")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _snapshot(root: Path) -> list[tuple[str, str, str]]:
    rows = []
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        rows.append((rel, "directory", "") if path.is_dir() else
                    (rel, "file", hashlib.sha256(path.read_bytes()).hexdigest()))
    return rows


def _resume(value: Mapping[str, Any], completed: Mapping[str, Any], point: str) -> dict[str, Any]:
    resumed = deepcopy(value)
    upstream = resumed["upstream_artifacts"]
    bundle = completed["canonical_artifact_bundle"]
    upstream.update({"resume_from": point, "observation_evidence_closure": None,
                     "decision_readiness_closure": None, "decision_authorization_closure": None})
    if point == "decision_readiness_closed":
        upstream["observation_evidence_closure"] = deepcopy(bundle["observation_evidence_closure"])
        upstream["decision_readiness_closure"] = deepcopy(bundle["decision_readiness_closure"])
    else:
        upstream["decision_authorization_closure"] = deepcopy(bundle["decision_authorization_closure"])
    return resumed


def _inventory() -> list[dict[str, Any]]:
    domains = ("capability_foundation", "activation_governance", "execution_control", "dry_run_bridge",
               "read_only_observation", "evidence_and_decision", "execution_infrastructure_integration",
               "governed_runtime")
    return [{"domain": name, "schema_version": SCHEMA_VERSION, "canonical": True,
             "permission_invariant": "all_false", "claim_invariant": "all_false"} for name in domains]


def validate_governed_capability_acceptance(value: Any) -> bool:
    if not isinstance(value, Mapping) or value.get("contract") != CONTRACT or value.get("schema_version") != SCHEMA_VERSION:
        return False
    copy = dict(value); fingerprint = copy.pop("acceptance_fingerprint", None)
    return fingerprint == _fingerprint(copy) and value.get("acceptance_status") in {"accepted", "blocked"}


def run_governed_capability_acceptance(runtime_input: Mapping[str, Any], *, source_head: str = "7ac2dd2e",
                                        regressions: Mapping[str, Any] | None = None) -> dict[str, Any]:
    source = deepcopy(runtime_input)
    root_value = source.get("explicit_inputs", {}).get("workspace_root")
    root = Path(root_value) if isinstance(root_value, str) and root_value else None
    before = _snapshot(root) if root is not None and root.is_dir() else []
    first = run_governed_capability_runtime(source)
    second = run_governed_capability_runtime(deepcopy(source))
    after = _snapshot(root) if root is not None and root.is_dir() else []
    positive = (first.get("runtime_state", {}).get("runtime_status") == "prepared"
                and first.get("prepared_transaction_handoff", {}).get("handoff_status") == "prepared"
                and first.get("transaction_integration_closure", {}).get("verification_status") == "verified_closed"
                and validate_governed_capability_runtime_closure(first.get("runtime_orchestration_closure", {})).valid)
    resume = {point: run_governed_capability_runtime(_resume(source, first, point)).get("runtime_state", {}).get("runtime_status") == "prepared"
              for point in RESUME_POINTS}
    stops = {}
    for point in STOP_POINTS:
        stopped = deepcopy(source); stopped["runtime_options"]["stop_after_stage"] = point
        outcome = run_governed_capability_runtime(stopped)
        stops[point] = outcome.get("runtime_state", {}).get("runtime_status") in ({"prepared"} if point in {"transaction_prepared", "runtime_closed"} else {"stopped"})
    tampered = deepcopy(source); tampered["upstream_artifacts"]["execution_authority"]["authority_id"] = "tampered"
    tampering = run_governed_capability_runtime(tampered).get("runtime_state", {}).get("runtime_status") == "blocked"
    regression = dict(regressions or {letter: {"passed": 0, "failed": 0, "skipped": 0, "duration": 0.0, "status": "not_run"}
                                          for letter in "ABCDEFG"})
    regression_ok = bool(regressions) and all(group.get("failed") == 0 and group.get("status") == "passed" for group in regression.values())
    side_effect_ok = before == after and first.get("audit_summary", {}).get("transaction_execute_called") is False
    claims = {name: False for name in CLAIMS}
    checks = [positive, first == second, all(resume.values()), all(stops.values()), tampering, side_effect_ok, regression_ok]
    report = {"contract": CONTRACT, "schema_version": SCHEMA_VERSION, "acceptance_id": "governed-capability-runtime-e2e-v1",
              "source_head": source_head, "runtime_contract_inventory": _inventory(),
              "tested_stage_order": list(first.get("runtime_state", {}).get("stage_states", {})),
              "positive_chain_result": {"passed": positive}, "determinism_result": {"passed": first == second},
              "tampering_result": {"passed": tampering}, "resume_result": {"passed": all(resume.values()), "variants": resume},
              "stop_after_stage_result": {"passed": all(stops.values()), "variants": stops},
              "side_effect_result": {"passed": side_effect_ok, "workspace_unchanged": before == after},
              "bounded_regression_result": regression,
              "prepared_transaction_handoff_reference": first.get("prepared_transaction_handoff", {}).get("handoff_id"),
              "transaction_integration_closure_reference": first.get("transaction_integration_closure", {}).get("integration_closure_id"),
              "runtime_closure_reference": first.get("runtime_orchestration_closure", {}).get("runtime_closure_id"),
              **claims, "limitations": ["read_only_and_transaction_preparation_only", "no_execution_or_commit"],
              "reasons": ["all_acceptance_checks_passed"] if all(checks) else [],
              "blocked_reasons": [] if all(checks) else ["one_or_more_acceptance_checks_failed_or_not_run"],
              "failure_reasons": [], "acceptance_status": "accepted" if all(checks) else "blocked", "merge_ready": all(checks)}
    report["acceptance_fingerprint"] = _fingerprint(report)
    return report


__all__ = ["CONTRACT", "run_governed_capability_acceptance", "validate_governed_capability_acceptance"]
