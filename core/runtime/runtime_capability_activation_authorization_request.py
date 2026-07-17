from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import canonical_json
from core.runtime.runtime_capability_activation_gate import AUTHORIZATION_CLASSES, FUTURE_CONSUMERS as GATE_FUTURE_CONSUMERS, REQUIRED_PROHIBITIONS

POLICY_SCHEMA = "zero.runtime.capability_activation_authorization_review_policy.v1"
REQUEST_SCHEMA = "zero.runtime.capability_activation_authorization_review_request.v1"
ELIGIBILITY_SCHEMA = "zero.runtime.capability_activation_authorization_review_eligibility.v1"
REVIEW_SCHEMA = "zero.runtime.capability_activation_authorization_review.v1"
HANDOFF_SCHEMA = "zero.runtime.capability_activation_authorization_review_handoff.v1"
MODES = frozenset({"validate_only", "evaluate_review", "prepare_review_handoff"})
STATUSES = frozenset({"validated", "reviewable", "blocked", "rejected", "invalid", "unsupported"})
REVIEWER_CLASSES = frozenset({"capability_runtime_activation_reviewer_v1"})
FUTURE_CONSUMERS = frozenset({"capability_runtime_activation_authorization_reviewer_v1"})
REQUIRED_CONDITIONS = frozenset({"valid_gate", "gate_allowed", "valid_authorization_metadata", "valid_linkage", "authorization_class_allowed", "activation_consumer_allowed", "runtime_inactive", "mutation_free", "authorization_absent", "token_absent", "activation_absent", "readonly_entitlement", "prohibitions_complete", "provenance_complete", "warnings_allowed", "reviewer_allowed"})

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
        "allowed_gate_statuses": ["allowed"],
        "require_gate_allowed": True,
        "allowed_authorization_classes": sorted(AUTHORIZATION_CLASSES),
        "allowed_activation_consumers": sorted(GATE_FUTURE_CONSUMERS),
        "allowed_future_consumers": sorted(FUTURE_CONSUMERS),
        "require_runtime_inactive": True,
        "require_mutation_free_chain": True,
        "require_authorization_not_issued": True,
        "require_token_not_issued": True,
        "require_activation_not_performed": True,
        "require_read_only_context_entitlement": True,
        "required_prohibited_actions": sorted(REQUIRED_PROHIBITIONS),
        "allow_warnings": False,
        "review_modes": sorted(MODES),
        "required_reviewer_class": "capability_runtime_activation_reviewer_v1",
        "safe_metadata": {"contract": "authorization_review_only"},
    }
    return _identified(base, "policy_id", "capability-activation-review-policy-")

def create_authorization_review_request(*, gate_decision: Mapping[str, Any], authorization_metadata: Mapping[str, Any], mode: str = "evaluate_review", reviewer_class: str = "capability_runtime_activation_reviewer_v1", future_consumer: str = "capability_runtime_activation_authorization_reviewer_v1", policy: Mapping[str, Any] | None = None, caller_metadata: Mapping[str, Any] | None = None, requested_at: str | None = None) -> dict[str, Any]:
    base = {
        "schema": REQUEST_SCHEMA,
        "gate_decision_id": gate_decision.get("decision_id"), "gate_decision_fingerprint": gate_decision.get("fingerprint"),
        "authorization_metadata_id": authorization_metadata.get("authorization_request_id"), "authorization_metadata_fingerprint": authorization_metadata.get("fingerprint"),
        "admission_decision_linkage": deepcopy(authorization_metadata.get("admission_decision_linkage")),
        "activation_handoff_linkage": deepcopy(authorization_metadata.get("activation_handoff_linkage")),
        "runtime_context_linkage": deepcopy(authorization_metadata.get("runtime_context_linkage")),
        "requested_authorization_class": authorization_metadata.get("requested_authorization_class"),
        "activation_consumer": authorization_metadata.get("future_activation_consumer"),
        "future_consumer": future_consumer,
        "review_mode": mode, "reviewer_class": reviewer_class,
        "policy": deepcopy(dict(policy or default_policy())), "caller_metadata": deepcopy(dict(caller_metadata or {})), "requested_at": requested_at,
    }
    return _identified(base, "request_id", "capability-activation-review-request-", frozenset({"requested_at"}))

def _eligibility(gate: Mapping[str, Any], metadata: Mapping[str, Any], policy: Mapping[str, Any], reviewer: Any, reasons: list[str]) -> dict[str, Any]:
    unsatisfied = sorted(set(reasons)); eligible = not unsatisfied
    base = {"schema": ELIGIBILITY_SCHEMA, "eligible": eligible, "status": "eligible" if eligible else "ineligible", "reason_codes": unsatisfied, "required_conditions": sorted(REQUIRED_CONDITIONS), "satisfied_conditions": sorted(REQUIRED_CONDITIONS) if eligible else [], "unsatisfied_conditions": unsatisfied, "gate_linkage": {"decision_id": gate.get("decision_id"), "fingerprint": gate.get("fingerprint")}, "policy_linkage": {"policy_id": policy.get("policy_id"), "fingerprint": policy.get("fingerprint")}, "reviewer_class": reviewer}
    return _identified(base, "eligibility_id", "capability-activation-review-eligibility-")

def _handoff(review: Mapping[str, Any], gate: Mapping[str, Any], metadata: Mapping[str, Any], prepared_at: str | None) -> dict[str, Any]:
    base = {
        "schema": HANDOFF_SCHEMA,
        "review_linkage": {"review_id": review.get("review_id"), "fingerprint": review.get("fingerprint")},
        "gate_decision_linkage": {"decision_id": gate.get("decision_id"), "fingerprint": gate.get("fingerprint")},
        "authorization_metadata_linkage": {"authorization_request_id": metadata.get("authorization_request_id"), "fingerprint": metadata.get("fingerprint")},
        "requested_authorization_class": review.get("requested_authorization_class"), "future_activation_consumer": review.get("future_consumer"), "reviewer_class": review.get("reviewer_class"),
        "review_status": review.get("review_status"), "reviewable": review.get("reviewable"),
        "required_external_approval": deepcopy(metadata.get("required_external_approval")),
        "prohibited_actions": sorted(REQUIRED_PROHIBITIONS), "safety_constraints": deepcopy(metadata.get("safety_constraints")), "provenance": deepcopy(metadata.get("provenance_chain")),
        "approval_issued": False, "authorization_issued": False, "token_issued": False, "activation_performed": False, "runtime_started": False, "mutation_performed": False, "prepared_at": prepared_at,
    }
    return _identified(base, "handoff_id", "capability-activation-review-handoff-", frozenset({"prepared_at", "review_linkage"}))

def review_activation_authorization(request: Mapping[str, Any], *, gate_decision: Mapping[str, Any], authorization_metadata: Mapping[str, Any], reviewed_at: str | None = None) -> dict[str, Any]:
    from core.runtime.runtime_capability_activation_authorization_request_validation import validate_authorization_review_request
    from core.runtime.runtime_capability_activation_gate_validation import validate_activation_authorization_request, validate_activation_gate_decision
    errors = list(validate_authorization_review_request(request).errors); policy = request.get("policy", {}) if isinstance(request, Mapping) else {}; reasons: list[str] = []
    if not validate_activation_gate_decision(gate_decision).valid: reasons.append("invalid_gate_decision")
    if not validate_activation_authorization_request(authorization_metadata).valid: reasons.append("invalid_authorization_metadata")
    if gate_decision.get("gate_status") not in policy.get("allowed_gate_statuses", []) or gate_decision.get("allowed") is not True: reasons.append("gate_not_allowed")
    links = (
        (request.get("gate_decision_id"), gate_decision.get("decision_id")), (request.get("gate_decision_fingerprint"), gate_decision.get("fingerprint")),
        (request.get("authorization_metadata_id"), authorization_metadata.get("authorization_request_id")), (request.get("authorization_metadata_fingerprint"), authorization_metadata.get("fingerprint")),
        (authorization_metadata.get("gate_decision_linkage", {}).get("decision_id"), gate_decision.get("decision_id")), (authorization_metadata.get("gate_decision_linkage", {}).get("fingerprint"), gate_decision.get("fingerprint")),
        (request.get("admission_decision_linkage"), authorization_metadata.get("admission_decision_linkage")), (request.get("activation_handoff_linkage"), authorization_metadata.get("activation_handoff_linkage")), (request.get("runtime_context_linkage"), authorization_metadata.get("runtime_context_linkage")),
    )
    if any(a != b for a, b in links): reasons.append("linkage_mismatch")
    if request.get("requested_authorization_class") != authorization_metadata.get("requested_authorization_class") or request.get("activation_consumer") != authorization_metadata.get("future_activation_consumer"): reasons.append("wrong_authorization_metadata")
    if request.get("requested_authorization_class") not in policy.get("allowed_authorization_classes", []): reasons.append("authorization_class_not_allowed")
    if request.get("activation_consumer") not in policy.get("allowed_activation_consumers", []): reasons.append("activation_consumer_not_allowed")
    chain = (gate_decision, authorization_metadata)
    if any(item.get("runtime_started") is True or item.get("runtime_start_requested") is True for item in chain): reasons.append("runtime_already_started")
    if any(item.get("mutation_performed") is True or item.get("mutation_classification") not in {None, "none"} for item in chain): reasons.append("mutation_already_performed")
    if any(item.get("authorization_issued") is True for item in chain): reasons.append("authorization_already_issued")
    if any(item.get("token_issued") is True for item in chain): reasons.append("token_already_issued")
    if any(item.get("activation_performed") is True for item in chain): reasons.append("activation_already_performed")
    if authorization_metadata.get("safety_constraints", {}).get("mutation_allowed") is not False or authorization_metadata.get("safety_constraints", {}).get("runtime_start_allowed") is not False: reasons.append("unsafe_intent")
    if not set(policy.get("required_prohibited_actions", [])) <= set(authorization_metadata.get("prohibited_actions", [])): reasons.append("incomplete_prohibited_actions")
    if not authorization_metadata.get("provenance_chain") or request.get("runtime_context_linkage") != authorization_metadata.get("runtime_context_linkage"): reasons.append("provenance_mismatch")
    warnings = list(gate_decision.get("warnings", []))
    if warnings and not policy.get("allow_warnings"): reasons.append("warnings_disallowed")
    mode=request.get("review_mode"); reviewer=request.get("reviewer_class"); future=request.get("future_consumer"); auth=request.get("requested_authorization_class"); activation_consumer=request.get("activation_consumer")
    unsupported = mode not in MODES or reviewer not in REVIEWER_CLASSES or future not in FUTURE_CONSUMERS or auth not in AUTHORIZATION_CLASSES or activation_consumer not in GATE_FUTURE_CONSUMERS or policy.get("schema") != POLICY_SCHEMA
    invalid_set={"invalid_gate_decision","invalid_authorization_metadata","linkage_mismatch","provenance_mismatch"}; rejected_set={"wrong_authorization_metadata"}; hazard_set={"runtime_already_started","mutation_already_performed","authorization_already_issued","token_already_issued","activation_already_performed","unsafe_intent","incomplete_prohibited_actions"}
    reasons=sorted(set(reasons)); eligibility=_eligibility(gate_decision,authorization_metadata,policy,reviewer,errors or reasons)
    status="unsupported" if unsupported else "rejected" if hazard_set.intersection(reasons) else "invalid" if errors or invalid_set.intersection(reasons) else "rejected" if rejected_set.intersection(reasons) else "validated" if mode=="validate_only" and not reasons else "blocked" if reasons else "reviewable"
    reviewable=status=="reviewable"; evidence={k:0 for k in ("gate_invocations","admission_invocations","consumer_invocations","integration_invocations","executor_invocations","planner_invocations","discovery_invocations","detection_invocations","authorization_invocations","approval_issuances","token_issuances","activation_invocations","runtime_startups","mission_agent_scheduler_worker_invocations","filesystem_mutations","subprocess_invocations","network_invocations","dynamic_imports","model_gpu_activations")}
    base={"schema":REVIEW_SCHEMA,"request_linkage":{"request_id":request.get("request_id"),"fingerprint":request.get("fingerprint")},"gate_linkage":{"decision_id":gate_decision.get("decision_id"),"fingerprint":gate_decision.get("fingerprint")},"authorization_metadata_linkage":{"authorization_request_id":authorization_metadata.get("authorization_request_id"),"fingerprint":authorization_metadata.get("fingerprint")},"eligibility_linkage":{"eligibility_id":eligibility.get("eligibility_id"),"fingerprint":eligibility.get("fingerprint")},"eligibility":eligibility,"review_status":status,"reviewable":reviewable,"blockers":errors or reasons,"warnings":warnings,"conditions":sorted(REQUIRED_CONDITIONS),"reviewer_class":reviewer,"requested_authorization_class":auth,"future_consumer":future,"review_handoff":None,"review_handoff_linkage":None,"safety_attestations":{"gate_not_reinvoked":True,"authorization_absent":True,"approval_absent":True,"token_absent":True,"activation_absent":True,"runtime_inactive":True,"mutation_free":True},"invocation_evidence":evidence,"approval_issued":False,"authorization_issued":False,"token_issued":False,"activation_performed":False,"runtime_started":False,"mutation_performed":False,"reviewed_at":reviewed_at}
    review=_identified(base,"review_id","capability-activation-review-",frozenset({"reviewed_at","review_handoff","review_handoff_linkage"}))
    if reviewable and mode=="prepare_review_handoff":
        handoff=_handoff(review,gate_decision,authorization_metadata,reviewed_at);review["review_handoff"]=handoff;review["review_handoff_linkage"]={"handoff_id":handoff["handoff_id"],"fingerprint":handoff["fingerprint"]}
    return json.loads(canonical_json(review))

__all__=["POLICY_SCHEMA","REQUEST_SCHEMA","ELIGIBILITY_SCHEMA","REVIEW_SCHEMA","HANDOFF_SCHEMA","MODES","STATUSES","REVIEWER_CLASSES","FUTURE_CONSUMERS","default_policy","create_authorization_review_request","review_activation_authorization"]
