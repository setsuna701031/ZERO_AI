from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_execution_validation import validate_execution_result
from core.runtime.runtime_capability_bootstrap_executor import HANDOFF_SCHEMA
from core.runtime.runtime_capability_bootstrap_integration import ELIGIBILITY_SCHEMA, EXPECTED_CONSUMER, FUTURE_CONSUMER, INTEGRATION_SCHEMA, MODES, POLICY_SCHEMA, REQUEST_SCHEMA, REQUIRED_PROHIBITIONS, RUNTIME_CONTEXT_SCHEMA, STATUSES, _OBSERVATIONS, _hash, _identity

@dataclass(frozen=True)
class BootstrapIntegrationValidationResult:
    valid: bool
    errors: tuple[str, ...]

def _safe(value: Any) -> bool:
    try: json.dumps(value, allow_nan=False)
    except (TypeError, ValueError): return False
    sensitive = {"username", "hostname", "api_key", "token", "access_token", "credential", "credentials", "exception", "traceback", "command", "callable", "provider", "provider_instance", "detector", "module", "class", "path", "environment"}
    def unsafe(item: Any) -> bool:
        if isinstance(item, Mapping): return any(str(k).casefold() in sensitive or unsafe(v) for k, v in item.items())
        if isinstance(item, (list, tuple)): return any(unsafe(v) for v in item)
        return not isinstance(item, (str, int, float, bool, type(None))) or (isinstance(item, str) and ("object at 0x" in item.casefold() or "traceback (most recent" in item.casefold()))
    return not unsafe(value)

def _policy_valid(policy: Any) -> bool:
    if not isinstance(policy, Mapping) or set(policy) != {"schema", "fingerprint", "allow_partial", "required_domains", "offline_required", "maximum_workers"}: return False
    if policy.get("schema") != POLICY_SCHEMA or not isinstance(policy.get("allow_partial"), bool) or not isinstance(policy.get("offline_required"), bool): return False
    if not isinstance(policy.get("required_domains"), list) or policy["required_domains"] != sorted(set(policy["required_domains"])): return False
    if isinstance(policy.get("maximum_workers"), bool) or not isinstance(policy.get("maximum_workers"), int) or not 1 <= policy["maximum_workers"] <= 64: return False
    return policy.get("fingerprint") == _hash({k: v for k, v in policy.items() if k != "fingerprint"})

def validate_integration_request(value: Any) -> BootstrapIntegrationValidationResult:
    required = {"schema", "request_id", "fingerprint", "handoff", "handoff_id", "handoff_fingerprint", "execution_result", "execution_result_id", "execution_result_fingerprint", "expected_consumer", "integration_mode", "requested_runtime_context_id", "policy", "metadata", "requested_at"}
    if not isinstance(value, Mapping): return BootstrapIntegrationValidationResult(False, ("request_not_object",))
    errors = [f"missing:{x}" for x in sorted(required-set(value))] + [f"unexpected:{x}" for x in sorted(set(value)-required)]
    if value.get("schema") != REQUEST_SCHEMA: errors.append("invalid_schema")
    if value.get("integration_mode") not in MODES: errors.append("unsupported_mode")
    if value.get("expected_consumer") != EXPECTED_CONSUMER: errors.append("wrong_consumer")
    result, handoff = value.get("execution_result"), value.get("handoff")
    if not validate_execution_result(result).valid: errors.append("invalid_execution_result")
    if not isinstance(handoff, Mapping) or handoff.get("schema") != HANDOFF_SCHEMA: errors.append("invalid_handoff")
    else:
        hfp = _hash({k: v for k, v in handoff.items() if k not in {"handoff_id", "fingerprint", "execution_result_linkage"}})
        if handoff.get("fingerprint") != hfp or handoff.get("handoff_id") != "capability-bootstrap-handoff-" + hfp[:24]: errors.append("handoff_identity_mismatch")
        if value.get("handoff_id") != handoff.get("handoff_id") or value.get("handoff_fingerprint") != handoff.get("fingerprint"): errors.append("handoff_linkage_mismatch")
        if handoff.get("execution_result_linkage") != {"execution_id": result.get("execution_id"), "fingerprint": result.get("fingerprint")}: errors.append("execution_result_linkage_mismatch")
        if handoff.get("allowed_future_consumer") != EXPECTED_CONSUMER: errors.append("wrong_consumer")
        if handoff.get("readiness") not in {"ready", "partial"}: errors.append("invalid_handoff_readiness")
        if handoff.get("mutation_classification") != "none" or handoff.get("runtime_started") is not False: errors.append("unsafe_handoff")
        if not REQUIRED_PROHIBITIONS <= set(handoff.get("prohibited_actions", [])): errors.append("missing_prohibition")
        if handoff.get("capability_context_linkage", {}).get("fingerprint") != result.get("capability_context", {}).get("fingerprint"): errors.append("capability_context_mismatch")
        if handoff.get("strategy_context_linkage", {}).get("fingerprint") != result.get("strategy_context", {}).get("fingerprint"): errors.append("strategy_context_mismatch")
    if isinstance(result, Mapping) and (value.get("execution_result_id") != result.get("execution_id") or value.get("execution_result_fingerprint") != result.get("fingerprint")): errors.append("execution_result_linkage_mismatch")
    if not _policy_valid(value.get("policy")): errors.append("invalid_policy")
    try:
        fp = _hash(_identity(value, frozenset({"request_id", "fingerprint", "requested_at"})))
        if value.get("fingerprint") != fp or value.get("request_id") != "capability-integration-request-" + fp[:24]: errors.append("request_identity_mismatch")
    except (TypeError, ValueError): errors.append("request_identity_invalid")
    if not _safe({"metadata": value.get("metadata")}): errors.append("unsafe_metadata")
    return BootstrapIntegrationValidationResult(not errors, tuple(dict.fromkeys(errors)))

def validate_runtime_context(value: Any) -> BootstrapIntegrationValidationResult:
    if not isinstance(value, Mapping): return BootstrapIntegrationValidationResult(False, ("context_not_object",))
    errors = []
    if value.get("schema") != RUNTIME_CONTEXT_SCHEMA: errors.append("invalid_schema")
    try:
        fp = _hash(_identity(value, frozenset({"runtime_context_id", "fingerprint"})))
        if value.get("fingerprint") != fp or value.get("runtime_context_id") != "capability-runtime-context-" + fp[:24]: errors.append("context_identity_mismatch")
    except (TypeError, ValueError): errors.append("context_identity_invalid")
    if value.get("runtime_started") is not False or value.get("safety_constraints", {}).get("mutation_allowed") is not False: errors.append("unsafe_context")
    if not _safe(value): errors.append("unsafe_or_non_json_context")
    return BootstrapIntegrationValidationResult(not errors, tuple(dict.fromkeys(errors)))

def validate_integration_record(value: Any) -> BootstrapIntegrationValidationResult:
    required = {"schema", "integration_id", "fingerprint", "request_linkage", "handoff_linkage", "execution_result_linkage", "capability_context_linkage", "strategy_context_linkage", "runtime_context", "runtime_context_id", "integration_status", "activation_eligibility", "activation_blockers", "warnings", "safety_attestations", "binding_metadata", "future_consumer", "runtime_started", "mutation_performed", "invocation_evidence", "integrated_at"}
    if not isinstance(value, Mapping): return BootstrapIntegrationValidationResult(False, ("integration_not_object",))
    errors = [f"missing:{x}" for x in sorted(required-set(value))] + [f"unexpected:{x}" for x in sorted(set(value)-required)]
    if value.get("schema") != INTEGRATION_SCHEMA or value.get("integration_status") not in STATUSES: errors.append("invalid_contract")
    context = value.get("runtime_context")
    if context is not None and not validate_runtime_context(context).valid: errors.append("invalid_runtime_context")
    if context is not None and value.get("runtime_context_id") != context.get("runtime_context_id"): errors.append("runtime_context_linkage_mismatch")
    eligibility = value.get("activation_eligibility")
    if not isinstance(eligibility, Mapping) or eligibility.get("schema") != ELIGIBILITY_SCHEMA: errors.append("invalid_eligibility")
    else:
        efp = _hash(_identity(eligibility, frozenset({"eligibility_id", "fingerprint"})))
        if eligibility.get("fingerprint") != efp or eligibility.get("eligibility_id") != "capability-eligibility-" + efp[:24]: errors.append("eligibility_identity_mismatch")
    if value.get("future_consumer") != FUTURE_CONSUMER or value.get("runtime_started") is not False or value.get("mutation_performed") is not False or value.get("safety_attestations", {}).get("mutation_classification") != "none": errors.append("unsafe_integration")
    if any(v != 0 for v in value.get("invocation_evidence", {}).values()): errors.append("unsafe_invocation_evidence")
    try:
        fp = _hash(_identity(value, _OBSERVATIONS | {"integration_id", "fingerprint"}))
        if value.get("fingerprint") != fp or value.get("integration_id") != "capability-integration-" + fp[:24]: errors.append("integration_identity_mismatch")
    except (TypeError, ValueError): errors.append("integration_identity_invalid")
    safe_view = {k: v for k, v in value.items() if k != "binding_metadata"}
    if not _safe(safe_view): errors.append("unsafe_or_non_json_integration")
    return BootstrapIntegrationValidationResult(not errors, tuple(dict.fromkeys(errors)))

__all__ = ["BootstrapIntegrationValidationResult", "validate_integration_request", "validate_runtime_context", "validate_integration_record"]
