from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import STEP_TYPES, canonical_json
from core.runtime.runtime_capability_bootstrap_plan_validation import validate_capability_bootstrap_plan
from core.runtime.runtime_capability_bootstrap_executor import BLOCK_REASONS, CONTEXT_SCHEMA, HANDOFF_SCHEMA, MODES, REQUEST_SCHEMA, RESULT_SCHEMA, STATUSES, STRATEGY_CONTEXT_SCHEMA, _hash, _identity, execution_result_identity

@dataclass(frozen=True)
class BootstrapExecutionValidationResult:
    valid: bool
    errors: tuple[str, ...]

def _json_safe(value: Any, *, reject_sensitive: bool = True) -> bool:
    try: json.dumps(value, allow_nan=False)
    except (TypeError, ValueError): return False
    sensitive = {"username", "hostname", "api_key", "token", "access_token", "credential", "credentials", "exception", "traceback", "command", "callable", "provider_instance"}
    def unsafe(item: Any) -> bool:
        if isinstance(item, Mapping): return any((reject_sensitive and str(k).casefold() in sensitive) or unsafe(v) for k, v in item.items())
        if isinstance(item, (list, tuple)): return any(unsafe(v) for v in item)
        return not isinstance(item, (str, int, float, bool, type(None))) or (isinstance(item, str) and ("object at 0x" in item.casefold() or "traceback (most recent" in item.casefold()))
    return not unsafe(value)

def validate_execution_request(value: Any) -> BootstrapExecutionValidationResult:
    required = {"schema", "request_id", "fingerprint", "bootstrap_plan", "bootstrap_plan_id", "bootstrap_plan_fingerprint", "requested_step_ids", "execution_policy", "artifacts", "provider_bindings", "requested_at"}
    if not isinstance(value, Mapping): return BootstrapExecutionValidationResult(False, ("request_not_object",))
    errors = [f"missing:{x}" for x in sorted(required-set(value))] + [f"unexpected:{x}" for x in sorted(set(value)-required)]
    if value.get("schema") != REQUEST_SCHEMA: errors.append("invalid_schema")
    plan = value.get("bootstrap_plan")
    if not validate_capability_bootstrap_plan(plan).valid: errors.append("invalid_plan")
    elif value.get("bootstrap_plan_id") != plan.get("plan_id") or value.get("bootstrap_plan_fingerprint") != plan.get("fingerprint"): errors.append("plan_linkage_mismatch")
    policy = value.get("execution_policy")
    if not isinstance(policy, Mapping) or set(policy) != {"mode", "dry_run", "mutation_allowed"} or policy.get("mode") not in MODES or policy.get("dry_run") is not True or policy.get("mutation_allowed") is not False: errors.append("invalid_execution_policy")
    ids = value.get("requested_step_ids")
    expected = [x.get("step_id") for x in plan.get("ordered_steps", [])] if isinstance(plan, Mapping) else []
    if not isinstance(ids, list) or ids != expected or len(ids) != len(set(ids)): errors.append("invalid_requested_steps")
    if not isinstance(value.get("artifacts"), Mapping) or not isinstance(value.get("provider_bindings"), Mapping): errors.append("invalid_inputs")
    try:
        fp = _hash(_identity(value, frozenset({"request_id", "fingerprint", "requested_at"})))
        if value.get("fingerprint") != fp or value.get("request_id") != "capability-bootstrap-request-" + fp[:24]: errors.append("request_identity_mismatch")
    except (TypeError, ValueError): errors.append("request_identity_invalid")
    if not _json_safe(value, reject_sensitive=False): errors.append("unsafe_or_non_json_value")
    return BootstrapExecutionValidationResult(not errors, tuple(dict.fromkeys(errors)))

def validate_execution_result(value: Any) -> BootstrapExecutionValidationResult:
    required = {"schema", "execution_id", "fingerprint", "request_linkage", "plan_linkage", "overall_status", "ordered_step_results", "blocked_reasons", "warnings", "capability_context", "strategy_context", "handoff_package", "safety_attestations", "invocation_evidence", "executed_at"}
    if not isinstance(value, Mapping): return BootstrapExecutionValidationResult(False, ("result_not_object",))
    errors = [f"missing:{x}" for x in sorted(required-set(value))] + [f"unexpected:{x}" for x in sorted(set(value)-required)]
    if value.get("schema") != RESULT_SCHEMA: errors.append("invalid_schema")
    if value.get("overall_status") not in STATUSES: errors.append("invalid_status")
    steps = value.get("ordered_step_results"); seen = []
    if not isinstance(steps, list): errors.append("invalid_steps")
    else:
        for index, step in enumerate(steps):
            if not isinstance(step, Mapping) or step.get("step_type") not in STEP_TYPES or step.get("execution_order") != index: errors.append(f"invalid_step:{index}"); continue
            if step.get("step_id") in seen: errors.append("duplicate_step")
            seen.append(step.get("step_id"))
            supplied = step.get("result_fingerprint")
            try:
                if supplied != _hash({k: v for k, v in step.items() if k != "result_fingerprint"}): errors.append(f"step_fingerprint_mismatch:{index}")
            except (TypeError, ValueError): errors.append(f"invalid_step:{index}")
    for key, schema in (("capability_context", CONTEXT_SCHEMA), ("strategy_context", STRATEGY_CONTEXT_SCHEMA), ("handoff_package", HANDOFF_SCHEMA)):
        item = value.get(key)
        if item is not None and (not isinstance(item, Mapping) or item.get("schema") != schema): errors.append(f"invalid_{key}")
    handoff = value.get("handoff_package")
    if isinstance(handoff, Mapping) and (handoff.get("allowed_future_consumer") != "runtime_bootstrap_executor_v1" or handoff.get("mutation_classification") != "none" or handoff.get("authorization_requirement") != "future_explicit_executor_authorization" or handoff.get("runtime_started") is not False): errors.append("invalid_handoff_safety")
    reasons = value.get("blocked_reasons")
    if not isinstance(reasons, list) or any(not isinstance(x, Mapping) or x.get("code") not in BLOCK_REASONS for x in reasons): errors.append("invalid_blocked_reasons")
    evidence = value.get("invocation_evidence")
    if not isinstance(evidence, Mapping) or any(v != 0 for v in evidence.values()): errors.append("unsafe_invocation_evidence")
    try:
        fp = _hash(execution_result_identity(value))
        if value.get("fingerprint") != fp or value.get("execution_id") != "capability-bootstrap-execution-" + fp[:24]: errors.append("result_identity_mismatch")
    except (TypeError, ValueError): errors.append("result_identity_invalid")
    if not _json_safe(value): errors.append("unsafe_or_non_json_value")
    return BootstrapExecutionValidationResult(not errors, tuple(dict.fromkeys(errors)))

__all__ = ["BootstrapExecutionValidationResult", "validate_execution_request", "validate_execution_result"]
