from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import canonical_json

DESCRIPTOR_SCHEMA = "zero.runtime.capability_bootstrap_consumer_descriptor.v1"
REQUEST_SCHEMA = "zero.runtime.capability_bootstrap_consumption_request.v1"
LEASE_SCHEMA = "zero.runtime.capability_context_lease.v1"
ELIGIBILITY_SCHEMA = "zero.runtime.capability_consumer_eligibility.v1"
RESULT_SCHEMA = "zero.runtime.capability_bootstrap_consumption_result.v1"
CONTEXT_VIEW_SCHEMA = "zero.runtime.capability_context_view.v1"
POLICY_SCHEMA = "zero.runtime.capability_bootstrap_consumption_policy.v1"
CONSUMER_ID = "runtime_bootstrap_consumer_v1"
INTEGRATION_CONSUMER = "capability_runtime_bootstrap_consumer_v1"
MODES = frozenset({"validate_only", "open_readonly_lease", "consume_context"})
SCOPES = frozenset({"capability_context_read", "strategy_context_read", "bootstrap_context_read", "eligibility_read", "combined_runtime_context_read"})
STATUSES = frozenset({"validated", "leased", "consumed", "blocked", "rejected", "invalid", "unsupported", "revoked"})
PROHIBITED_ACTIONS = ("activate", "execute", "filesystem", "install", "mutate", "network", "provider_control", "runtime_startup", "write")

def _hash(value: Any) -> str: return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
def _identified(value: Mapping[str, Any], id_key: str, prefix: str, excluded: frozenset[str] = frozenset()) -> dict[str, Any]:
    result = deepcopy(dict(value)); identity = {k: v for k, v in result.items() if k not in excluded | {id_key, "fingerprint"}}
    fp = _hash(identity); result["fingerprint"] = fp; result[id_key] = prefix + fp[:24]
    return json.loads(canonical_json(result))

def default_policy() -> dict[str, Any]:
    base = {"schema": POLICY_SCHEMA, "read_only_required": True, "runtime_start_allowed": False, "mutation_allowed": False, "ttl_seconds": None, "required_prohibited_actions": list(PROHIBITED_ACTIONS)}
    base["fingerprint"] = _hash(base); return json.loads(canonical_json(base))

def consumer_descriptor() -> dict[str, Any]:
    base = {"schema": DESCRIPTOR_SCHEMA, "consumer_id": CONSUMER_ID, "consumer_version": "1.0", "contract_version": "1", "supported_integration_schema": "zero.runtime.capability_bootstrap_integration.v1", "supported_runtime_context_schema": "zero.runtime.capability_runtime_context.v1", "allowed_consumption_modes": sorted(MODES), "allowed_lease_scopes": sorted(SCOPES), "requires_accepted_integration": True, "requires_eligible_activation_decision": True, "read_only_required": True, "mutation_classification": "none", "safe_symbolic_metadata": {"integration_consumer_mapping": INTEGRATION_CONSUMER}}
    fp = _hash(base); return json.loads(canonical_json({**base, "fingerprint": fp}))

def create_consumption_request(*, integration: Mapping[str, Any], runtime_context: Mapping[str, Any], mode: str = "validate_only", requested_lease_scope: str = "combined_runtime_context_read", consumer_id: str = CONSUMER_ID, policy: Mapping[str, Any] | None = None, metadata: Mapping[str, Any] | None = None, requested_at: str | None = None, lease_id: str | None = None) -> dict[str, Any]:
    base = {"schema": REQUEST_SCHEMA, "integration_id": integration.get("integration_id"), "integration_fingerprint": integration.get("fingerprint"), "runtime_context_id": runtime_context.get("runtime_context_id"), "runtime_context_fingerprint": runtime_context.get("fingerprint"), "consumer_id": consumer_id, "mode": mode, "requested_lease_scope": requested_lease_scope, "policy": deepcopy(dict(policy or default_policy())), "metadata": deepcopy(dict(metadata or {})), "requested_at": requested_at, "lease_id": lease_id}
    return _identified(base, "request_id", "capability-consumption-request-", frozenset({"requested_at"}))

def _eligibility(request: Mapping[str, Any], integration: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    required = ["accepted_integration", "eligible_activation", "inactive_runtime", "no_mutation", "consumer_mapping", "valid_context_linkage", "supported_mode", "supported_scope", "read_only_policy", "required_prohibitions"]
    reasons: list[str] = []
    from core.runtime.runtime_capability_bootstrap_integration_validation import validate_integration_record, validate_runtime_context
    if not validate_integration_record(integration).valid: reasons.append("invalid_integration")
    if integration.get("integration_status") != "accepted": reasons.append("integration_not_accepted")
    if integration.get("activation_eligibility", {}).get("eligible") is not True: reasons.append("activation_not_eligible")
    if integration.get("runtime_started") is not False or context.get("runtime_started") is not False: reasons.append("runtime_already_started")
    if integration.get("mutation_performed") is not False: reasons.append("mutation_already_performed")
    if integration.get("future_consumer") != INTEGRATION_CONSUMER or request.get("consumer_id") != CONSUMER_ID: reasons.append("wrong_consumer")
    if not validate_runtime_context(context).valid or integration.get("runtime_context_id") != context.get("runtime_context_id") or integration.get("runtime_context", {}).get("fingerprint") != context.get("fingerprint") or request.get("runtime_context_id") != context.get("runtime_context_id") or request.get("runtime_context_fingerprint") != context.get("fingerprint"): reasons.append("runtime_context_mismatch")
    if request.get("integration_id") != integration.get("integration_id") or request.get("integration_fingerprint") != integration.get("fingerprint"): reasons.append("integration_linkage_mismatch")
    if request.get("mode") not in MODES: reasons.append("unsupported_mode")
    if request.get("requested_lease_scope") not in SCOPES: reasons.append("unsupported_scope")
    policy = request.get("policy", {})
    if policy.get("read_only_required") is not True or policy.get("mutation_allowed") is not False or policy.get("runtime_start_allowed") is not False: reasons.append("unsafe_policy")
    if not set(PROHIBITED_ACTIONS) <= set(policy.get("required_prohibited_actions", [])): reasons.append("missing_prohibition")
    reasons = sorted(set(reasons)); satisfied = [x for x in required if not reasons]
    base = {"schema": ELIGIBILITY_SCHEMA, "eligible": not reasons, "status": "eligible" if not reasons else "blocked", "consumer_id": request.get("consumer_id"), "integration_linkage": {"integration_id": integration.get("integration_id"), "fingerprint": integration.get("fingerprint")}, "runtime_context_linkage": {"runtime_context_id": context.get("runtime_context_id"), "fingerprint": context.get("fingerprint")}, "required_conditions": required, "satisfied_conditions": satisfied, "unsatisfied_conditions": reasons, "reason_codes": reasons, "policy_linkage": {"fingerprint": policy.get("fingerprint")}}
    result = _identified(base, "eligibility_id", "capability-consumer-eligibility-"); result.pop("eligibility_id")
    return result

def _lease(request: Mapping[str, Any], integration: Mapping[str, Any], context: Mapping[str, Any], *, issued_at: str | None = None, expires_at: str | None = None) -> dict[str, Any]:
    base = {"schema": LEASE_SCHEMA, "consumer_id": CONSUMER_ID, "request_linkage": {"request_id": request.get("request_id"), "fingerprint": request.get("fingerprint")}, "integration_linkage": {"integration_id": integration.get("integration_id"), "fingerprint": integration.get("fingerprint")}, "runtime_context_linkage": {"runtime_context_id": context.get("runtime_context_id"), "fingerprint": context.get("fingerprint")}, "lease_scope": request.get("requested_lease_scope"), "permissions": ["read_detached_context"], "prohibited_actions": list(PROHIBITED_ACTIONS), "read_only": True, "mutation_allowed": False, "runtime_start_allowed": False, "issued_status": "issued", "lease_status": "active", "ttl_policy_linkage": {"ttl_seconds": request.get("policy", {}).get("ttl_seconds"), "policy_fingerprint": request.get("policy", {}).get("fingerprint")}, "revocation_status": "not_revoked", "safe_warnings": [], "issued_at": issued_at, "expires_at": expires_at}
    return _identified(base, "lease_id", "capability-context-lease-", frozenset({"issued_at", "expires_at", "lease_status", "revocation_status"}))

class ProcessLocalLeaseRegistry:
    def __init__(self) -> None: self._leases: dict[str, dict[str, Any]] = {}; self._states: dict[str, str] = {}
    def issue(self, lease: Mapping[str, Any]) -> str:
        detached = json.loads(canonical_json(lease)); lease_id = detached["lease_id"]; current = self._leases.get(lease_id)
        if current is not None and current != detached: raise ValueError("lease_conflict")
        if self._states.get(lease_id) == "revoked": raise ValueError("lease_revoked")
        self._leases[lease_id] = detached; self._states[lease_id] = "active"; return "existing" if current is not None else "issued"
    def resolve(self, lease_id: str) -> dict[str, Any] | None:
        value = self._leases.get(lease_id)
        if value is None: return None
        result = deepcopy(value); state = self._states.get(lease_id, "active"); result["lease_status"] = state; result["revocation_status"] = "revoked" if state == "revoked" else "not_revoked"; return result
    def revoke(self, lease_id: str) -> bool:
        if lease_id not in self._leases: return False
        self._states[lease_id] = "revoked"; return True
    def load_explicit(self, lease: Mapping[str, Any]) -> str:
        """Load caller-supplied lease state without issuing or reactivating it."""
        detached = json.loads(canonical_json(lease)); lease_id = detached["lease_id"]; current = self._leases.get(lease_id)
        canonical = deepcopy(detached); canonical["lease_status"] = "active"; canonical["revocation_status"] = "not_revoked"
        if current is not None and current != canonical: raise ValueError("lease_conflict")
        state = "revoked" if detached.get("lease_status") == "revoked" or detached.get("revocation_status") == "revoked" else "active"
        if self._states.get(lease_id) == "revoked" and state == "active": raise ValueError("lease_revoked")
        self._leases[lease_id] = canonical; self._states[lease_id] = state; return state
    def list_symbolic_metadata(self) -> list[dict[str, str]]: return [{"lease_id": key, "fingerprint": value["fingerprint"], "lease_status": self._states[key]} for key, value in sorted(self._leases.items())]
    def validate_state(self, lease_id: str) -> bool: return lease_id in self._leases and self._states.get(lease_id) == "active"

PROCESS_LOCAL_LEASES = ProcessLocalLeaseRegistry()

def _context_view(context: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(canonical_json({"schema": CONTEXT_VIEW_SCHEMA, "runtime_context_id": context.get("runtime_context_id"), "runtime_context_fingerprint": context.get("fingerprint"), "profile_linkage": deepcopy(context.get("capability_profile_linkage")), "strategy_linkage": deepcopy(context.get("strategy_linkage")), "available_domains": deepcopy(context.get("available_domains", [])), "resource_constraints": deepcopy(context.get("resource_constraints", [])), "worker_bounds": deepcopy(context.get("worker_bounds", {})), "execution_mode": context.get("execution_mode"), "network_mode": context.get("network_mode"), "accelerator_policy": context.get("accelerator_policy"), "tool_summary": deepcopy(context.get("tool_availability", [])), "environment_summary": deepcopy(context.get("environment_summary", {})), "warnings": deepcopy(context.get("warnings", [])), "safety_constraints": deepcopy(context.get("safety_constraints", {})), "provenance_chain": deepcopy(context.get("provenance_chain", {}))}))

def consume_capability_bootstrap(request: Mapping[str, Any], *, integration: Mapping[str, Any], runtime_context: Mapping[str, Any], lease: Mapping[str, Any] | None = None, registry: ProcessLocalLeaseRegistry | None = None, consumed_at: str | None = None) -> dict[str, Any]:
    registry = registry or PROCESS_LOCAL_LEASES
    from core.runtime.runtime_capability_bootstrap_consumer_validation import validate_consumption_request, validate_lease
    request_errors = validate_consumption_request(request).errors
    eligibility = _eligibility(request, integration, runtime_context)
    status = "validated"; blockers = list(eligibility["reason_codes"]); output_lease = None; view = None
    if request.get("mode") not in MODES: status = "unsupported"
    elif request_errors: status = "invalid"; blockers = list(request_errors)
    elif not eligibility["eligible"]: status = "rejected" if any(x in blockers for x in ("wrong_consumer", "runtime_already_started", "mutation_already_performed")) else "blocked"
    elif request.get("mode") == "open_readonly_lease":
        output_lease = _lease(request, integration, runtime_context)
        try: registry.issue(output_lease); status = "leased"
        except ValueError as exc: status = "revoked" if str(exc) == "lease_revoked" else "rejected"; blockers = [str(exc)]
    elif request.get("mode") == "consume_context":
        if lease is not None:
            try: registry.load_explicit(lease)
            except ValueError as exc: status = "revoked" if str(exc) == "lease_revoked" else "rejected"; blockers = [str(exc)]
        candidate = registry.resolve(request.get("lease_id")) if request.get("lease_id") else None
        validation = validate_lease(candidate)
        if status in {"rejected", "revoked"}: pass
        elif not validation.valid: status = "invalid"; blockers = list(validation.errors)
        elif candidate.get("lease_id") != request.get("lease_id") or candidate.get("integration_linkage", {}).get("integration_id") != integration.get("integration_id") or candidate.get("runtime_context_linkage", {}).get("runtime_context_id") != runtime_context.get("runtime_context_id"): status = "rejected"; blockers = ["lease_linkage_mismatch"]
        elif not registry.validate_state(candidate["lease_id"]): status = "revoked" if registry.resolve(candidate["lease_id"]) else "rejected"; blockers = ["lease_not_active"]
        else: status = "consumed"; output_lease = deepcopy(candidate); view = _context_view(runtime_context)
    evidence = {key: 0 for key in ("discovery_invocations", "detector_invocations", "provider_invocations", "profile_builder_invocations", "strategy_selection_invocations", "registry_mutations", "planner_invocations", "executor_invocations", "integration_invocations", "runtime_startups", "mission_agent_scheduler_worker_invocations", "filesystem_mutations", "subprocess_invocations", "network_invocations", "dynamic_imports", "model_gpu_activations")}
    base = {"schema": RESULT_SCHEMA, "request_linkage": {"request_id": request.get("request_id"), "fingerprint": request.get("fingerprint")}, "consumer_descriptor_linkage": {"consumer_id": CONSUMER_ID, "fingerprint": consumer_descriptor()["fingerprint"]}, "integration_linkage": {"integration_id": integration.get("integration_id"), "fingerprint": integration.get("fingerprint")}, "runtime_context_linkage": {"runtime_context_id": runtime_context.get("runtime_context_id"), "fingerprint": runtime_context.get("fingerprint")}, "eligibility": eligibility, "lease": output_lease, "status": status, "read_only_context_view": view, "warnings": [], "blocked_reasons": blockers, "safety_attestations": {"read_only": True, "runtime_started": False, "mutation_performed": False}, "invocation_evidence": evidence, "runtime_started": False, "mutation_performed": False, "consumed_at": consumed_at}
    return _identified(base, "consumption_id", "capability-consumption-", frozenset({"consumed_at"}))

__all__ = ["DESCRIPTOR_SCHEMA", "REQUEST_SCHEMA", "LEASE_SCHEMA", "ELIGIBILITY_SCHEMA", "RESULT_SCHEMA", "CONTEXT_VIEW_SCHEMA", "POLICY_SCHEMA", "CONSUMER_ID", "MODES", "SCOPES", "STATUSES", "PROHIBITED_ACTIONS", "ProcessLocalLeaseRegistry", "PROCESS_LOCAL_LEASES", "default_policy", "consumer_descriptor", "create_consumption_request", "consume_capability_bootstrap"]
