from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import STEP_TYPES, canonical_json
from core.runtime.runtime_capability_bootstrap_plan_validation import validate_capability_bootstrap_plan
from core.runtime.runtime_capability_detection_validation import validate_capability_detection
from core.runtime.runtime_capability_provider_discovery_validation import validate_capability_provider_discovery
from core.runtime.runtime_capability_registry_validation import validate_capability_registry
from core.runtime.runtime_capability_strategy_validation import validate_capability_strategy
from core.runtime.runtime_capability_validation import validate_capability_profile

REQUEST_SCHEMA = "zero.runtime.capability_bootstrap_execution_request.v1"
RESULT_SCHEMA = "zero.runtime.capability_bootstrap_execution_result.v1"
CONTEXT_SCHEMA = "zero.runtime.capability_bootstrap_context.v1"
STRATEGY_CONTEXT_SCHEMA = "zero.runtime.capability_bootstrap_strategy_context.v1"
HANDOFF_SCHEMA = "zero.runtime.capability_bootstrap_handoff.v1"
MODES = frozenset({"validation_only", "prepare_handoff"})
STATUSES = frozenset({"completed", "partial", "blocked", "invalid", "unsupported", "failed"})
BLOCK_REASONS = frozenset({"invalid_request", "invalid_plan", "invalid_artifact", "linkage_mismatch", "missing_dependency", "required_provider_unbound", "required_domain_unavailable", "strategy_incompatible", "unsupported_mode", "unsupported_step"})
_TIME_KEYS = frozenset({"requested_at", "executed_at", "started_at", "completed_at"})

def _hash(value: Any) -> str: return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
def _identity(value: Mapping[str, Any], excluded: set[str] | frozenset[str]) -> dict[str, Any]: return {k: deepcopy(v) for k, v in value.items() if k not in excluded}
def _identified(value: dict[str, Any], id_key: str, prefix: str, excluded: set[str] | frozenset[str]) -> dict[str, Any]:
    fp = _hash(_identity(value, excluded | {id_key, "fingerprint"})); value["fingerprint"] = fp; value[id_key] = prefix + fp[:24]
    return json.loads(canonical_json(value))

def execution_result_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    identity = _identity(value, _TIME_KEYS | {"execution_id", "fingerprint"})
    handoff = identity.get("handoff_package")
    if isinstance(handoff, Mapping): identity["handoff_package"] = {k: deepcopy(v) for k, v in handoff.items() if k != "execution_result_linkage"}
    return identity

def create_execution_request(*, plan: Mapping[str, Any], artifacts: Mapping[str, Any], mode: str = "validation_only", requested_step_ids: list[str] | None = None, provider_bindings: Mapping[str, Any] | None = None, requested_at: str | None = None) -> dict[str, Any]:
    base = {"schema": REQUEST_SCHEMA, "bootstrap_plan": deepcopy(dict(plan)), "bootstrap_plan_id": plan.get("plan_id"), "bootstrap_plan_fingerprint": plan.get("fingerprint"), "requested_step_ids": deepcopy(requested_step_ids) if requested_step_ids is not None else [x.get("step_id") for x in plan.get("ordered_steps", [])], "execution_policy": {"mode": mode, "dry_run": True, "mutation_allowed": False}, "artifacts": deepcopy(dict(artifacts)), "provider_bindings": deepcopy(dict(provider_bindings or {})), "requested_at": requested_at}
    return _identified(base, "request_id", "capability-bootstrap-request-", _TIME_KEYS)

def _context(profile: Mapping[str, Any], detection: Mapping[str, Any], strategy: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    results = detection.get("results", []) if isinstance(detection.get("results"), list) else []
    available = sorted(x.get("domain") for x in results if isinstance(x, Mapping) and x.get("status") in {"available", "partial"} and isinstance(x.get("domain"), str))
    constraints = deepcopy(profile.get("constraints", [])) if isinstance(profile.get("constraints", []), list) else []
    tools = sorted(str(x.get("name")) for x in profile.get("available_tools", []) if isinstance(x, Mapping) and x.get("name"))
    execution = strategy.get("execution_preferences", {}) if isinstance(strategy.get("execution_preferences"), Mapping) else {}
    base = {"schema": CONTEXT_SCHEMA, "profile_linkage": {"profile_id": profile.get("profile_id"), "fingerprint": profile.get("fingerprint")}, "available_domains": available, "resource_constraints": constraints, "tool_availability": tools, "execution_environment": {"mode": strategy.get("recommended_mode")}, "network_policy": "offline_only" if plan.get("policy_constraints", {}).get("offline_only") else "policy_controlled", "strategy_linkage": {"strategy_id": strategy.get("strategy_id"), "fingerprint": strategy.get("fingerprint")}, "worker_bounds": {"max_workers": execution.get("max_workers")}, "warnings": deepcopy(plan.get("warnings", [])), "provenance_fingerprints": {"detection": detection.get("fingerprint"), "profile": profile.get("fingerprint"), "strategy": strategy.get("fingerprint")}}
    return _identified(base, "context_id", "capability-bootstrap-context-", frozenset())

def _strategy_context(strategy: Mapping[str, Any], profile: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    execution = strategy.get("execution_preferences", {}) if isinstance(strategy.get("execution_preferences"), Mapping) else {}
    mode = strategy.get("recommended_mode")
    base = {"schema": STRATEGY_CONTEXT_SCHEMA, "strategy_id": strategy.get("strategy_id"), "strategy_fingerprint": strategy.get("fingerprint"), "strategy_mode": mode, "worker_bounds": {"max_workers": execution.get("max_workers")}, "execution_mode": execution.get("execution_mode", "bounded"), "network_mode": "offline" if plan.get("policy_constraints", {}).get("offline_only") else "policy_controlled", "accelerator_policy": "disabled" if mode == "cpu_only" else "symbolic_available", "constrained_flags": deepcopy(strategy.get("constraints", [])), "source_profile_linkage": {"profile_id": profile.get("profile_id"), "fingerprint": profile.get("fingerprint")}, "policy_constraints": deepcopy(plan.get("policy_constraints", {}))}
    return _identified(base, "strategy_context_id", "capability-bootstrap-strategy-context-", frozenset())

def _step_result(step: Mapping[str, Any], status: str, output: Mapping[str, Any], reason: str | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
    base = {"step_id": step.get("step_id"), "step_fingerprint": step.get("fingerprint"), "step_type": step.get("step_type"), "execution_order": step.get("order"), "status": status, "observation": {"started": True, "completed": True}, "symbolic_output": deepcopy(dict(output)), "blocked_reason": reason, "warning_codes": sorted(warnings or []), "input_fingerprint_linkage": sorted({x.get("fingerprint") for x in step.get("input_artifact_references", {}).values() if isinstance(x, Mapping) and x.get("fingerprint")})}
    base["result_fingerprint"] = _hash(base); return json.loads(canonical_json(base))

def execute_capability_bootstrap(request: Mapping[str, Any]) -> dict[str, Any]:
    plan = request.get("bootstrap_plan", {}) if isinstance(request, Mapping) else {}; mode = request.get("execution_policy", {}).get("mode") if isinstance(request, Mapping) and isinstance(request.get("execution_policy"), Mapping) else None
    status, reasons, warnings = "completed", [], []
    if mode not in MODES: status, reasons = "unsupported", [{"code": "unsupported_mode"}]
    from core.runtime.runtime_capability_bootstrap_execution_validation import validate_execution_request
    validation = validate_execution_request(request)
    if not validation.valid and status == "completed": status, reasons = "invalid", [{"code": "invalid_request"}]
    plan_validation = validate_capability_bootstrap_plan(plan)
    if not plan_validation.valid and status == "completed": status, reasons = "invalid", [{"code": "invalid_plan"}]
    artifacts = request.get("artifacts", {}) if isinstance(request, Mapping) and isinstance(request.get("artifacts"), Mapping) else {}
    validators = {"validate_discovery": ("discovery", validate_capability_provider_discovery), "validate_detection": ("detection", validate_capability_detection), "validate_profile": ("profile", validate_capability_profile), "validate_strategy": ("strategy", validate_capability_strategy), "validate_registry": ("registry", validate_capability_registry)}
    step_results, completed, capability, strategy_context = [], set(), None, None
    for step in plan.get("ordered_steps", []) if isinstance(plan, Mapping) else []:
        if status in {"invalid", "unsupported", "blocked", "failed"}: break
        st = step.get("step_type")
        if st not in STEP_TYPES: status, reasons = "unsupported", [{"code": "unsupported_step"}]; break
        if any(dep not in completed for dep in step.get("dependency_step_ids", [])): status, reasons = "blocked", [{"code": "missing_dependency"}]; break
        if st in validators:
            name, validator = validators[st]; artifact = artifacts.get(name)
            try: valid = artifact is not None and validator(artifact).valid
            except Exception: valid = False
            if not valid: status, reasons = "invalid", [{"code": "invalid_artifact", "artifact": name}]; step_results.append(_step_result(step, "invalid", {"validated": False}, "invalid_artifact")); break
            output = {"validated": True, "artifact": name}
        elif st == "verify_provider_bindings":
            required = set(plan.get("policy_constraints", {}).get("required_domains", [])); bindings = request.get("provider_bindings", {})
            selected = artifacts.get("discovery", {}).get("selected_providers", [])
            states = [{"domain": x.get("domain"), "provider_id": x.get("provider_id"), "status": bindings.get(x.get("provider_id"), x.get("binding_status", "missing"))} for x in selected if isinstance(x, Mapping)]
            bad_required = [x for x in states if x["domain"] in required and x["status"] != "bound"]
            bad_optional = [x for x in states if x["domain"] not in required and x["status"] != "bound"]
            if bad_required: status, reasons = "blocked", [{"code": "required_provider_unbound"}]; step_results.append(_step_result(step, "blocked", {"bindings": states}, "required_provider_unbound")); break
            if bad_optional: status = "partial"; warnings.append({"code": "optional_provider_unbound"})
            output = {"bindings": states}
        elif st == "verify_required_domains":
            results = {x.get("domain"): x.get("status") for x in artifacts.get("detection", {}).get("results", []) if isinstance(x, Mapping)}
            missing = [x for x in plan.get("policy_constraints", {}).get("required_domains", []) if results.get(x) not in {"available", "partial"}]
            if missing: status, reasons = "blocked", [{"code": "required_domain_unavailable", "domains": missing}]; step_results.append(_step_result(step, "blocked", {"available": sorted(results)}, "required_domain_unavailable")); break
            output = {"verified_domains": sorted(results)}
        elif st == "prepare_runtime_capability_context": capability = _context(artifacts["profile"], artifacts["detection"], artifacts["strategy"], plan); output = {"context_id": capability["context_id"], "fingerprint": capability["fingerprint"]}
        elif st == "prepare_strategy_context": strategy_context = _strategy_context(artifacts["strategy"], artifacts["profile"], plan); output = {"strategy_context_id": strategy_context["strategy_context_id"], "fingerprint": strategy_context["fingerprint"]}
        else: output = {"sealed": st == "seal_bootstrap_inputs", "handoff_prepared": st == "handoff_to_bootstrap_executor"}
        step_results.append(_step_result(step, "completed", output)); completed.add(step.get("step_id"))
    handoff = None
    if mode == "prepare_handoff" and status in {"completed", "partial"} and capability and strategy_context:
        base = {"schema": HANDOFF_SCHEMA, "execution_result_linkage": None, "plan_linkage": {"plan_id": plan.get("plan_id"), "fingerprint": plan.get("fingerprint")}, "capability_context_linkage": {"context_id": capability["context_id"], "fingerprint": capability["fingerprint"]}, "strategy_context_linkage": {"strategy_context_id": strategy_context["strategy_context_id"], "fingerprint": strategy_context["fingerprint"]}, "readiness": "ready" if status == "completed" else "partial", "allowed_future_consumer": "runtime_bootstrap_executor_v1", "prohibited_actions": ["mutation", "runtime_startup", "provider_invocation", "network", "subprocess"], "authorization_requirement": "future_explicit_executor_authorization", "mutation_classification": "none", "runtime_started": False}
        handoff = _identified(base, "handoff_id", "capability-bootstrap-handoff-", frozenset({"execution_result_linkage"}))
    evidence = {"detector_invocations": 0, "provider_invocations": 0, "discovery_invocations": 0, "strategy_selection_invocations": 0, "registry_mutations": 0, "runtime_startups": 0, "filesystem_mutations": 0, "subprocess_invocations": 0, "network_invocations": 0, "dynamic_imports": 0}
    base = {"schema": RESULT_SCHEMA, "request_linkage": {"request_id": request.get("request_id"), "fingerprint": request.get("fingerprint")}, "plan_linkage": {"plan_id": plan.get("plan_id"), "fingerprint": plan.get("fingerprint")}, "overall_status": status, "ordered_step_results": step_results, "blocked_reasons": reasons, "warnings": warnings, "capability_context": capability, "strategy_context": strategy_context, "handoff_package": handoff, "safety_attestations": {"validation_only": True, "mutation_performed": False, "runtime_started": False}, "invocation_evidence": evidence, "executed_at": request.get("executed_at")}
    fp = _hash(execution_result_identity(base)); base["fingerprint"] = fp; base["execution_id"] = "capability-bootstrap-execution-" + fp[:24]
    if handoff is not None: base["handoff_package"]["execution_result_linkage"] = {"execution_id": base["execution_id"], "fingerprint": fp}
    return json.loads(canonical_json(base))

__all__ = ["REQUEST_SCHEMA", "RESULT_SCHEMA", "CONTEXT_SCHEMA", "STRATEGY_CONTEXT_SCHEMA", "HANDOFF_SCHEMA", "MODES", "STATUSES", "BLOCK_REASONS", "create_execution_request", "execute_capability_bootstrap", "execution_result_identity"]
