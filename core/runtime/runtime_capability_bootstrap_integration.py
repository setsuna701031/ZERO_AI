from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import canonical_json

REQUEST_SCHEMA = "zero.runtime.capability_bootstrap_integration_request.v1"
INTEGRATION_SCHEMA = "zero.runtime.capability_bootstrap_integration.v1"
RUNTIME_CONTEXT_SCHEMA = "zero.runtime.capability_runtime_context.v1"
ELIGIBILITY_SCHEMA = "zero.runtime.capability_activation_eligibility.v1"
POLICY_SCHEMA = "zero.runtime.capability_bootstrap_integration_policy.v1"
MODES = frozenset({"validate_only", "prepare_context", "accept_handoff"})
STATUSES = frozenset({"validated", "prepared", "accepted", "blocked", "rejected", "invalid", "unsupported"})
EXPECTED_CONSUMER = "runtime_bootstrap_executor_v1"
FUTURE_CONSUMER = "capability_runtime_bootstrap_consumer_v1"
REQUIRED_PROHIBITIONS = frozenset({"mutation", "runtime_startup", "provider_invocation", "network", "subprocess"})
_OBSERVATIONS = frozenset({"requested_at", "integrated_at", "binding_metadata"})

def _hash(value: Any) -> str: return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
def _identity(value: Mapping[str, Any], excluded: set[str] | frozenset[str]) -> dict[str, Any]: return {k: deepcopy(v) for k, v in value.items() if k not in excluded}
def _identified(value: dict[str, Any], id_key: str, prefix: str, excluded: set[str] | frozenset[str] = frozenset()) -> dict[str, Any]:
    fp = _hash(_identity(value, excluded | {id_key, "fingerprint"})); value["fingerprint"] = fp; value[id_key] = prefix + fp[:24]
    return json.loads(canonical_json(value))

def default_policy() -> dict[str, Any]:
    base = {"schema": POLICY_SCHEMA, "allow_partial": False, "required_domains": ["cpu"], "offline_required": True, "maximum_workers": 8}
    base["fingerprint"] = _hash(base); return json.loads(canonical_json(base))

def create_integration_request(*, execution_result: Mapping[str, Any], mode: str = "validate_only", expected_consumer: str = EXPECTED_CONSUMER, runtime_context_id: str | None = None, policy: Mapping[str, Any] | None = None, metadata: Mapping[str, Any] | None = None, requested_at: str | None = None) -> dict[str, Any]:
    handoff = execution_result.get("handoff_package") or {}
    base = {"schema": REQUEST_SCHEMA, "handoff": deepcopy(handoff), "handoff_id": handoff.get("handoff_id"), "handoff_fingerprint": handoff.get("fingerprint"), "execution_result": deepcopy(dict(execution_result)), "execution_result_id": execution_result.get("execution_id"), "execution_result_fingerprint": execution_result.get("fingerprint"), "expected_consumer": expected_consumer, "integration_mode": mode, "requested_runtime_context_id": runtime_context_id, "policy": deepcopy(dict(policy or default_policy())), "metadata": deepcopy(dict(metadata or {})), "requested_at": requested_at}
    return _identified(base, "request_id", "capability-integration-request-", frozenset({"requested_at"}))

class RuntimeCapabilityContextContainer:
    def __init__(self) -> None: self._bindings: dict[str, dict[str, Any]] = {}
    def bind(self, runtime_context_id: str, value: Mapping[str, Any]) -> str:
        detached = json.loads(canonical_json(value)); current = self._bindings.get(runtime_context_id)
        if current is not None and current != detached: raise ValueError("runtime_context_conflict")
        self._bindings[runtime_context_id] = detached; return "existing" if current is not None else "bound"
    def resolve(self, runtime_context_id: str) -> dict[str, Any] | None: return deepcopy(self._bindings.get(runtime_context_id))
    def list_symbolic_bindings(self) -> list[dict[str, str]]: return [{"runtime_context_id": key, "fingerprint": value.get("fingerprint")} for key, value in sorted(self._bindings.items())]
    def clear(self, runtime_context_id: str) -> bool: return self._bindings.pop(runtime_context_id, None) is not None
    def snapshot(self) -> dict[str, Any]: return {"binding_count": len(self._bindings), "bindings": self.list_symbolic_bindings(), "process_local": True}

PROCESS_LOCAL_CONTEXTS = RuntimeCapabilityContextContainer()

def _runtime_context(result: Mapping[str, Any], policy: Mapping[str, Any], requested_id: str | None) -> dict[str, Any]:
    capability, strategy = result.get("capability_context") or {}, result.get("strategy_context") or {}
    supplied_workers = strategy.get("worker_bounds", {}).get("max_workers")
    worker_limit = supplied_workers if isinstance(supplied_workers, int) and not isinstance(supplied_workers, bool) else 1
    base = {"schema": RUNTIME_CONTEXT_SCHEMA, "capability_profile_linkage": deepcopy(capability.get("profile_linkage")), "strategy_linkage": {"strategy_id": strategy.get("strategy_id"), "fingerprint": strategy.get("strategy_fingerprint")}, "available_domains": deepcopy(capability.get("available_domains", [])), "resource_constraints": deepcopy(capability.get("resource_constraints", [])), "worker_bounds": {"max_workers": worker_limit}, "execution_mode": strategy.get("execution_mode"), "network_mode": strategy.get("network_mode"), "accelerator_policy": strategy.get("accelerator_policy"), "tool_availability": deepcopy(capability.get("tool_availability", [])), "environment_summary": deepcopy(capability.get("execution_environment", {})), "warnings": deepcopy(capability.get("warnings", [])), "provenance_chain": deepcopy(capability.get("provenance_fingerprints", {})), "safety_constraints": {"mutation_allowed": False, "runtime_start_allowed": False, "offline_required": policy.get("offline_required")}, "runtime_started": False}
    value = _identified(base, "runtime_context_id", "capability-runtime-context-")
    if requested_id is not None and requested_id != value["runtime_context_id"]: raise ValueError("runtime_context_id_mismatch")
    return value

def _eligibility(context: Mapping[str, Any] | None, policy: Mapping[str, Any], *, accepted: bool, reasons: list[str]) -> dict[str, Any]:
    required = ["handoff_accepted", "contexts_valid", "required_domains_available", "offline_policy_consistent", "worker_bounds_valid", "accelerator_policy_consistent", "mutation_prohibited", "runtime_inactive"]
    unsatisfied = list(reasons)
    if context:
        missing = sorted(set(policy.get("required_domains", [])) - set(context.get("available_domains", [])))
        if missing: unsatisfied.append("required_domain_missing")
        workers = context.get("worker_bounds", {}).get("max_workers")
        if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= policy.get("maximum_workers", 8): unsatisfied.append("worker_bounds_invalid")
        if policy.get("offline_required") and context.get("network_mode") != "offline": unsatisfied.append("offline_policy_mismatch")
        if context.get("accelerator_policy") != "disabled" and "accelerator" not in context.get("available_domains", []): unsatisfied.append("accelerator_evidence_mismatch")
    if not accepted: unsatisfied.append("handoff_not_accepted")
    unsatisfied = sorted(set(unsatisfied)); satisfied = sorted(set(required) - {"handoff_accepted" if "handoff_not_accepted" in unsatisfied else "", "required_domains_available" if "required_domain_missing" in unsatisfied else "", "offline_policy_consistent" if "offline_policy_mismatch" in unsatisfied else "", "worker_bounds_valid" if "worker_bounds_invalid" in unsatisfied else "", "accelerator_policy_consistent" if "accelerator_evidence_mismatch" in unsatisfied else ""})
    base = {"schema": ELIGIBILITY_SCHEMA, "eligible": not unsatisfied, "status": "eligible" if not unsatisfied else "blocked", "reason_codes": unsatisfied, "required_conditions": required, "satisfied_conditions": satisfied, "unsatisfied_conditions": unsatisfied, "policy_linkage": {"fingerprint": policy.get("fingerprint")}, "context_linkage": {"runtime_context_id": context.get("runtime_context_id"), "fingerprint": context.get("fingerprint")} if context else None, "strategy_linkage": deepcopy(context.get("strategy_linkage")) if context else None}
    return _identified(base, "eligibility_id", "capability-eligibility-")

def integrate_capability_bootstrap(request: Mapping[str, Any], *, container: RuntimeCapabilityContextContainer | None = None, integrated_at: str | None = None) -> dict[str, Any]:
    container = container or PROCESS_LOCAL_CONTEXTS; result = request.get("execution_result", {}) if isinstance(request, Mapping) else {}; handoff = request.get("handoff", {}) if isinstance(request, Mapping) else {}; policy = request.get("policy", {}) if isinstance(request, Mapping) else {}; mode = request.get("integration_mode") if isinstance(request, Mapping) else None
    status, blockers, warnings, context = "validated", [], [], None
    from core.runtime.runtime_capability_bootstrap_integration_validation import validate_integration_request
    errors = validate_integration_request(request).errors
    if mode not in MODES: status, blockers = "unsupported", ["unsupported_mode"]
    elif errors: status, blockers = "invalid", ["invalid_request"]
    elif result.get("overall_status") in {"invalid", "failed", "unsupported"}: status, blockers = "rejected", ["execution_result_rejected"]
    elif result.get("overall_status") == "blocked": status, blockers = "blocked", ["execution_result_blocked"]
    elif handoff.get("readiness") == "partial" and not policy.get("allow_partial"): status, blockers = "blocked", ["partial_not_allowed"]
    else:
        try: context = _runtime_context(result, policy, request.get("requested_runtime_context_id"))
        except ValueError: status, blockers = "invalid", ["runtime_context_id_mismatch"]
        if context and mode == "prepare_context": status = "prepared"
        elif context and mode == "accept_handoff": status = "accepted" if result.get("overall_status") == "completed" or policy.get("allow_partial") else "prepared"
    accepted = status == "accepted"; eligibility = _eligibility(context, policy, accepted=accepted, reasons=blockers)
    if status in {"prepared", "accepted"} and not eligibility["eligible"] and eligibility["reason_codes"] != ["handoff_not_accepted"]:
        status, blockers = "blocked", eligibility["reason_codes"]
        eligibility = _eligibility(context, policy, accepted=False, reasons=blockers)
    binding_state = "not_bound"
    if context and mode in {"prepare_context", "accept_handoff"} and status in {"prepared", "accepted"}:
        try: binding_state = container.bind(context["runtime_context_id"], context)
        except ValueError: status, blockers, binding_state = "rejected", ["runtime_context_conflict"], "conflict"; eligibility = _eligibility(context, policy, accepted=False, reasons=blockers)
    evidence = {key: 0 for key in ("discovery_invocations", "detector_invocations", "provider_invocations", "profile_builder_invocations", "strategy_selection_invocations", "registry_mutations", "bootstrap_planner_invocations", "bootstrap_executor_invocations", "runtime_startups", "filesystem_mutations", "subprocess_invocations", "network_invocations", "dynamic_imports", "model_gpu_activations")}
    base = {"schema": INTEGRATION_SCHEMA, "request_linkage": {"request_id": request.get("request_id"), "fingerprint": request.get("fingerprint")}, "handoff_linkage": {"handoff_id": handoff.get("handoff_id"), "fingerprint": handoff.get("fingerprint")}, "execution_result_linkage": {"execution_id": result.get("execution_id"), "fingerprint": result.get("fingerprint")}, "capability_context_linkage": deepcopy(handoff.get("capability_context_linkage")), "strategy_context_linkage": deepcopy(handoff.get("strategy_context_linkage")), "runtime_context": context, "runtime_context_id": context.get("runtime_context_id") if context else None, "integration_status": status, "activation_eligibility": eligibility, "activation_blockers": blockers, "warnings": warnings, "safety_attestations": {"mutation_classification": "none", "runtime_started": False, "mutation_performed": False}, "binding_metadata": {"state": binding_state, "process_local": True}, "future_consumer": FUTURE_CONSUMER, "runtime_started": False, "mutation_performed": False, "invocation_evidence": evidence, "integrated_at": integrated_at}
    return _identified(base, "integration_id", "capability-integration-", _OBSERVATIONS)

__all__ = ["REQUEST_SCHEMA", "INTEGRATION_SCHEMA", "RUNTIME_CONTEXT_SCHEMA", "ELIGIBILITY_SCHEMA", "POLICY_SCHEMA", "MODES", "STATUSES", "EXPECTED_CONSUMER", "FUTURE_CONSUMER", "RuntimeCapabilityContextContainer", "PROCESS_LOCAL_CONTEXTS", "default_policy", "create_integration_request", "integrate_capability_bootstrap"]
