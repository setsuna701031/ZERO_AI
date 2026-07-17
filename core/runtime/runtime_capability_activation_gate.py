from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import canonical_json
from core.runtime.runtime_capability_bootstrap_consumer import PROHIBITED_ACTIONS

POLICY_SCHEMA = "zero.runtime.capability_activation_gate_policy.v1"
REQUEST_SCHEMA = "zero.runtime.capability_activation_gate_request.v1"
DECISION_SCHEMA = "zero.runtime.capability_activation_gate_decision.v1"
AUTHORIZATION_REQUEST_SCHEMA = "zero.runtime.capability_activation_authorization_request.v1"
MODES = frozenset({"validate_only", "evaluate_gate", "prepare_authorization_request"})
STATUSES = frozenset({"validated", "allowed", "blocked", "rejected", "invalid", "unsupported"})
AUTHORIZATION_CLASSES = frozenset({"capability_runtime_activation_authorization_v1"})
FUTURE_CONSUMERS = frozenset({"capability_runtime_activation_controller_v1"})
REQUIRED_PROHIBITIONS = frozenset(PROHIBITED_ACTIONS) | {"authorize", "issue_token", "activate"}
REQUIRED_CONDITIONS = frozenset({"admitted_decision", "sealed_handoff", "valid_linkage", "active_readonly_lease", "runtime_inactive", "mutation_free", "no_authorization", "no_token", "required_domains", "strategy_allowed", "worker_bounds", "offline_safe", "accelerator_consistent", "resource_constraints", "prohibitions_complete", "warnings_allowed", "consumer_allowed", "authorization_class_allowed", "provenance_consistent"})

def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

def _identified(value: Mapping[str, Any], key: str, prefix: str, excluded: frozenset[str] = frozenset()) -> dict[str, Any]:
    result = deepcopy(dict(value))
    fingerprint = _hash({k: v for k, v in result.items() if k not in excluded | {key, "fingerprint"}})
    result["fingerprint"] = fingerprint
    result[key] = prefix + fingerprint[:24]
    return json.loads(canonical_json(result))

def default_policy() -> dict[str, Any]:
    base = {
        "schema": POLICY_SCHEMA,
        "allowed_admission_statuses": ["admitted"],
        "require_admitted_decision": True,
        "require_activation_handoff": True,
        "require_runtime_inactive": True,
        "require_mutation_free_chain": True,
        "require_no_authorization_issued": True,
        "require_no_token_issued": True,
        "required_future_consumer": "capability_runtime_activation_controller_v1",
        "allowed_strategy_modes": ["bounded"],
        "required_domains": ["cpu"],
        "worker_bounds_policy": {"minimum": 1, "maximum": 8},
        "offline_safe_requirement": True,
        "accelerator_policy": "disabled",
        "power_constraint_policy": "must_not_be_violated",
        "memory_storage_constraint_policy": "must_not_be_violated",
        "lease_requirement": {"active": True, "not_revoked": True, "read_only": True, "mutation_allowed": False, "runtime_start_allowed": False},
        "prohibited_actions_requirement": sorted(REQUIRED_PROHIBITIONS),
        "allow_warnings": False,
        "allow_partial_chain": False,
        "allowed_gate_modes": sorted(MODES),
        "allowed_authorization_classes": sorted(AUTHORIZATION_CLASSES),
        "safe_symbolic_metadata": {"contract": "activation_gate_only"},
    }
    return _identified(base, "policy_id", "capability-activation-gate-policy-")

def create_activation_gate_request(*, admission_decision: Mapping[str, Any], activation_handoff: Mapping[str, Any] | None, consumption_result: Mapping[str, Any], lease: Mapping[str, Any], integration: Mapping[str, Any], runtime_context: Mapping[str, Any], mode: str = "evaluate_gate", authorization_class: str = "capability_runtime_activation_authorization_v1", future_consumer: str = "capability_runtime_activation_controller_v1", policy: Mapping[str, Any] | None = None, caller_metadata: Mapping[str, Any] | None = None, requested_at: str | None = None) -> dict[str, Any]:
    handoff = activation_handoff or {}
    base = {
        "schema": REQUEST_SCHEMA,
        "admission_decision_id": admission_decision.get("decision_id"), "admission_decision_fingerprint": admission_decision.get("fingerprint"),
        "activation_handoff_id": handoff.get("handoff_id"), "activation_handoff_fingerprint": handoff.get("fingerprint"),
        "consumption_result_id": consumption_result.get("consumption_id"), "consumption_result_fingerprint": consumption_result.get("fingerprint"),
        "lease_id": lease.get("lease_id"), "lease_fingerprint": lease.get("fingerprint"),
        "integration_id": integration.get("integration_id"), "integration_fingerprint": integration.get("fingerprint"),
        "runtime_context_id": runtime_context.get("runtime_context_id"), "runtime_context_fingerprint": runtime_context.get("fingerprint"),
        "gate_mode": mode, "requested_authorization_class": authorization_class, "requested_future_activation_consumer": future_consumer,
        "policy": deepcopy(dict(policy or default_policy())), "caller_metadata": deepcopy(dict(caller_metadata or {})), "requested_at": requested_at,
    }
    return _identified(base, "request_id", "capability-activation-gate-request-", frozenset({"requested_at"}))

def _authorization_request(decision: Mapping[str, Any], admission: Mapping[str, Any], handoff: Mapping[str, Any], context: Mapping[str, Any], prepared_at: str | None) -> dict[str, Any]:
    base = {
        "schema": AUTHORIZATION_REQUEST_SCHEMA,
        "gate_decision_linkage": {"decision_id": decision.get("decision_id"), "fingerprint": decision.get("fingerprint")},
        "admission_decision_linkage": {"decision_id": admission.get("decision_id"), "fingerprint": admission.get("fingerprint")},
        "activation_handoff_linkage": {"handoff_id": handoff.get("handoff_id"), "fingerprint": handoff.get("fingerprint")},
        "runtime_context_linkage": {"runtime_context_id": context.get("runtime_context_id"), "fingerprint": context.get("fingerprint")},
        "requested_authorization_class": decision.get("requested_authorization_class"), "future_activation_consumer": decision.get("future_activation_consumer"),
        "requested_action": "consider_capability_runtime_activation", "mutation_classification": "none", "runtime_start_requested": False,
        "authorization_issued": False, "token_issued": False, "activation_performed": False,
        "required_external_approval": {"required": True, "approval_class": "future_explicit_approval"},
        "prohibited_actions": sorted(REQUIRED_PROHIBITIONS),
        "safety_constraints": {"mutation_allowed": False, "runtime_start_allowed": False, "offline_required": True},
        "provenance_chain": deepcopy(handoff.get("provenance_chain", {})), "prepared_at": prepared_at,
    }
    return _identified(base, "authorization_request_id", "capability-activation-authorization-request-", frozenset({"prepared_at", "gate_decision_linkage"}))

def evaluate_activation_gate(request: Mapping[str, Any], *, admission_decision: Mapping[str, Any], activation_handoff: Mapping[str, Any] | None, consumption_result: Mapping[str, Any], lease: Mapping[str, Any], integration: Mapping[str, Any], runtime_context: Mapping[str, Any], evaluated_at: str | None = None) -> dict[str, Any]:
    from core.runtime.runtime_capability_activation_gate_validation import validate_activation_gate_request
    from core.runtime.runtime_capability_bootstrap_admission_validation import validate_activation_handoff, validate_admission_decision
    errors = list(validate_activation_gate_request(request).errors); policy = request.get("policy", {}) if isinstance(request, Mapping) else {}; handoff = activation_handoff or {}; blockers: list[str] = []
    if not validate_admission_decision(admission_decision).valid: blockers.append("invalid_admission_decision")
    if not validate_activation_handoff(handoff).valid: blockers.append("invalid_activation_handoff")
    if admission_decision.get("admission_status") not in policy.get("allowed_admission_statuses", []) or admission_decision.get("admitted") is not True: blockers.append("admission_not_admitted")
    links = ((request.get("admission_decision_id"), admission_decision.get("decision_id")), (request.get("admission_decision_fingerprint"), admission_decision.get("fingerprint")), (request.get("activation_handoff_id"), handoff.get("handoff_id")), (request.get("activation_handoff_fingerprint"), handoff.get("fingerprint")), (request.get("consumption_result_id"), consumption_result.get("consumption_id")), (request.get("consumption_result_fingerprint"), consumption_result.get("fingerprint")), (request.get("lease_id"), lease.get("lease_id")), (request.get("lease_fingerprint"), lease.get("fingerprint")), (request.get("integration_id"), integration.get("integration_id")), (request.get("integration_fingerprint"), integration.get("fingerprint")), (request.get("runtime_context_id"), runtime_context.get("runtime_context_id")), (request.get("runtime_context_fingerprint"), runtime_context.get("fingerprint")))
    handoff_links = ((handoff.get("admission_decision_linkage", {}).get("decision_id"), admission_decision.get("decision_id")), (handoff.get("admission_decision_linkage", {}).get("fingerprint"), admission_decision.get("fingerprint")), (handoff.get("consumption_result_linkage", {}).get("consumption_id"), consumption_result.get("consumption_id")), (handoff.get("consumption_result_linkage", {}).get("fingerprint"), consumption_result.get("fingerprint")), (handoff.get("lease_linkage", {}).get("lease_id"), lease.get("lease_id")), (handoff.get("lease_linkage", {}).get("fingerprint"), lease.get("fingerprint")), (handoff.get("integration_linkage", {}).get("integration_id"), integration.get("integration_id")), (handoff.get("integration_linkage", {}).get("fingerprint"), integration.get("fingerprint")), (handoff.get("runtime_context_linkage", {}).get("runtime_context_id"), runtime_context.get("runtime_context_id")), (handoff.get("runtime_context_linkage", {}).get("fingerprint"), runtime_context.get("fingerprint")))
    if any(a != b for a, b in links + handoff_links): blockers.append("linkage_mismatch")
    if handoff.get("future_consumer") != "capability_runtime_activation_gate_v1": blockers.append("wrong_handoff_consumer")
    if lease.get("lease_status") != "active" or lease.get("revocation_status") != "not_revoked": blockers.append("revoked_or_inactive_lease")
    if lease.get("read_only") is not True or lease.get("mutation_allowed") is not False or lease.get("runtime_start_allowed") is not False: blockers.append("unsafe_lease_permission")
    chain = (admission_decision, handoff, consumption_result, lease, integration, runtime_context)
    if any("runtime_started" in item and item.get("runtime_started") is not False for item in chain if isinstance(item, Mapping)): blockers.append("runtime_already_started")
    if any(item.get("mutation_performed") is True for item in chain if isinstance(item, Mapping)): blockers.append("mutation_already_performed")
    if any(item.get("authorization_issued") is True for item in chain if isinstance(item, Mapping)): blockers.append("authorization_already_issued")
    if any(item.get("token_issued") is True for item in chain if isinstance(item, Mapping)): blockers.append("token_already_issued")
    if any(item.get("activation_performed") is True for item in chain if isinstance(item, Mapping)): blockers.append("activation_already_performed")
    if set(policy.get("required_domains", [])) - set(runtime_context.get("available_domains", [])): blockers.append("required_domain_missing")
    if runtime_context.get("execution_mode") not in policy.get("allowed_strategy_modes", []): blockers.append("strategy_not_allowed")
    workers = runtime_context.get("worker_bounds", {}).get("max_workers"); bounds = policy.get("worker_bounds_policy", {})
    if isinstance(workers, bool) or not isinstance(workers, int) or not bounds.get("minimum", 1) <= workers <= bounds.get("maximum", 8): blockers.append("worker_bounds_invalid")
    if policy.get("offline_safe_requirement") and runtime_context.get("network_mode") != "offline": blockers.append("offline_mismatch")
    if runtime_context.get("accelerator_policy") != policy.get("accelerator_policy"): blockers.append("accelerator_mismatch")
    constraints = runtime_context.get("resource_constraints", [])
    if any(isinstance(x, Mapping) and (x.get("violated") is True or x.get("status") in {"violated", "insufficient", "blocked"}) for x in constraints): blockers.append("resource_constraint_violated")
    if not set(policy.get("prohibited_actions_requirement", [])) <= set(handoff.get("prohibited_actions", [])) or not set(PROHIBITED_ACTIONS) <= set(lease.get("prohibited_actions", [])): blockers.append("missing_prohibited_action")
    if handoff.get("provenance_chain") != runtime_context.get("provenance_chain"): blockers.append("provenance_mismatch")
    warnings = list(admission_decision.get("warnings", [])) + list(handoff.get("warnings", []))
    if warnings and not policy.get("allow_warnings"): blockers.append("warnings_not_allowed")
    mode = request.get("gate_mode"); auth_class = request.get("requested_authorization_class"); future = request.get("requested_future_activation_consumer")
    unsupported = mode not in MODES or auth_class not in AUTHORIZATION_CLASSES or future not in FUTURE_CONSUMERS or policy.get("schema") != POLICY_SCHEMA
    invalid_set = {"invalid_admission_decision", "invalid_activation_handoff", "linkage_mismatch", "provenance_mismatch"}
    rejected_set = {"wrong_handoff_consumer", "revoked_or_inactive_lease", "unsafe_lease_permission", "runtime_already_started", "mutation_already_performed", "authorization_already_issued", "token_already_issued", "activation_already_performed", "missing_prohibited_action"}
    blockers = sorted(set(blockers)); status = "unsupported" if unsupported else "invalid" if errors or invalid_set.intersection(blockers) else "rejected" if rejected_set.intersection(blockers) else "validated" if mode == "validate_only" and not blockers else "blocked" if blockers else "allowed"
    allowed = status == "allowed"; unsatisfied = errors or blockers; satisfied = sorted(REQUIRED_CONDITIONS - set(unsatisfied)) if allowed else []
    evidence = {k: 0 for k in ("discovery_invocations", "detector_invocations", "provider_invocations", "profile_builder_invocations", "strategy_selection_invocations", "registry_mutations", "planner_invocations", "executor_invocations", "integration_invocations", "consumer_invocations", "admission_invocations", "runtime_startups", "mission_agent_scheduler_worker_invocations", "approval_invocations", "authorization_invocations", "token_issuances", "activation_invocations", "filesystem_mutations", "subprocess_invocations", "network_invocations", "dynamic_imports", "model_gpu_activations")}
    base = {"schema": DECISION_SCHEMA, "request_linkage": {"request_id": request.get("request_id"), "fingerprint": request.get("fingerprint")}, "policy_linkage": {"policy_id": policy.get("policy_id"), "fingerprint": policy.get("fingerprint")}, "admission_decision_linkage": {"decision_id": admission_decision.get("decision_id"), "fingerprint": admission_decision.get("fingerprint")}, "activation_handoff_linkage": {"handoff_id": handoff.get("handoff_id"), "fingerprint": handoff.get("fingerprint")}, "consumption_result_linkage": {"consumption_id": consumption_result.get("consumption_id"), "fingerprint": consumption_result.get("fingerprint")}, "lease_linkage": {"lease_id": lease.get("lease_id"), "fingerprint": lease.get("fingerprint")}, "integration_linkage": {"integration_id": integration.get("integration_id"), "fingerprint": integration.get("fingerprint")}, "runtime_context_linkage": {"runtime_context_id": runtime_context.get("runtime_context_id"), "fingerprint": runtime_context.get("fingerprint")}, "gate_status": status, "allowed": allowed, "blockers": unsatisfied, "warnings": warnings, "required_conditions": sorted(REQUIRED_CONDITIONS), "satisfied_conditions": satisfied, "unsatisfied_conditions": unsatisfied, "requested_authorization_class": auth_class, "future_activation_consumer": future, "authorization_request": None, "authorization_request_linkage": None, "safety_attestations": {"runtime_inactive": True, "mutation_free": True, "authorization_absent": True, "token_absent": True, "activation_absent": True}, "invocation_evidence": evidence, "runtime_started": False, "mutation_performed": False, "authorization_issued": False, "token_issued": False, "activation_performed": False, "evaluated_at": evaluated_at}
    decision = _identified(base, "decision_id", "capability-activation-gate-decision-", frozenset({"evaluated_at", "authorization_request", "authorization_request_linkage"}))
    if allowed and mode == "prepare_authorization_request":
        authorization = _authorization_request(decision, admission_decision, handoff, runtime_context, evaluated_at); decision["authorization_request"] = authorization; decision["authorization_request_linkage"] = {"authorization_request_id": authorization["authorization_request_id"], "fingerprint": authorization["fingerprint"]}
    return json.loads(canonical_json(decision))

__all__ = ["POLICY_SCHEMA", "REQUEST_SCHEMA", "DECISION_SCHEMA", "AUTHORIZATION_REQUEST_SCHEMA", "MODES", "STATUSES", "AUTHORIZATION_CLASSES", "FUTURE_CONSUMERS", "REQUIRED_PROHIBITIONS", "default_policy", "create_activation_gate_request", "evaluate_activation_gate"]
