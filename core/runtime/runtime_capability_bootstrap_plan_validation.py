from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_plan import BLOCK_REASONS, OWNERS, POLICY_SCHEMA, READINESS, SCHEMA, SCOPES, STEP_TYPES, _unsafe, compute_plan_fingerprint, compute_policy_fingerprint, compute_step_fingerprint, normalize_policy


@dataclass(frozen=True)
class BootstrapPlanValidationResult:
    valid: bool
    errors: tuple[str, ...]


def validate_capability_bootstrap_plan(value: Any) -> BootstrapPlanValidationResult:
    required = {"schema", "plan_id", "fingerprint", "readiness", "source_artifact_linkage", "requested_bootstrap_scope", "ordered_steps", "blocked_reasons", "warnings", "unresolved_requirements", "policy_constraints", "safety_constraints", "expected_outputs", "planning_metadata", "planned_at"}
    if not isinstance(value, Mapping): return BootstrapPlanValidationResult(False, ("plan_not_object",))
    errors = [f"missing:{x}" for x in sorted(required - set(value))] + [f"unexpected:{x}" for x in sorted(set(value) - required)]
    if value.get("schema") != SCHEMA: errors.append("invalid_schema")
    if value.get("readiness") not in READINESS: errors.append("invalid_readiness")
    if value.get("requested_bootstrap_scope") not in SCOPES: errors.append("invalid_scope")
    linkage = value.get("source_artifact_linkage")
    if not isinstance(linkage, Mapping) or set(linkage) != {"discovery", "detection", "profile", "strategy", "registry"}: errors.append("invalid_source_linkage")
    elif any(item is not None and (not isinstance(item, Mapping) or set(item) != {"schema", "artifact_id", "fingerprint"} or not all(isinstance(item.get(k), str) and item.get(k) for k in ("schema", "artifact_id", "fingerprint")) or re.fullmatch(r"[0-9a-f]{64}", item.get("fingerprint", "")) is None) for item in linkage.values()): errors.append("invalid_source_linkage")
    policy = value.get("policy_constraints")
    if not isinstance(policy, Mapping) or policy.get("schema") != POLICY_SCHEMA: errors.append("invalid_policy")
    else:
        try:
            if policy.get("fingerprint") != compute_policy_fingerprint(policy): errors.append("policy_fingerprint_mismatch")
            normalize_policy(policy)
        except (TypeError, ValueError): errors.append("invalid_policy")
    steps = value.get("ordered_steps"); ids: list[str] = []
    if not isinstance(steps, list): errors.append("invalid_steps")
    else:
        for index, step in enumerate(steps):
            if not isinstance(step, Mapping): errors.append(f"invalid_step:{index}"); continue
            required_step = {"step_id", "fingerprint", "step_type", "order", "dependency_step_ids", "input_artifact_references", "expected_output_type", "required", "execution_ownership", "authorization_requirement", "mutation_classification", "status", "blocked_reason", "metadata"}
            if set(step) != required_step: errors.append(f"invalid_step_fields:{index}")
            if step.get("step_type") not in STEP_TYPES or step.get("order") != index or step.get("execution_ownership") not in OWNERS: errors.append(f"invalid_step:{index}")
            if step.get("mutation_classification") not in {"read_only", "future_mutation"} or step.get("authorization_requirement") not in {"none", "future_explicit_executor_authorization"} or not isinstance(step.get("required"), bool): errors.append(f"invalid_step_contract:{index}")
            if step.get("status") not in {"planned", "blocked"} or (step.get("blocked_reason") is not None and step.get("blocked_reason") not in BLOCK_REASONS): errors.append(f"invalid_step_status:{index}")
            deps = step.get("dependency_step_ids")
            if not isinstance(deps, list) or deps != sorted(set(deps)): errors.append(f"invalid_dependencies:{index}")
            try:
                fingerprint = compute_step_fingerprint(step)
                if step.get("fingerprint") != fingerprint or step.get("step_id") != "bootstrap-step-" + fingerprint[:24]: errors.append(f"step_identity_mismatch:{index}")
            except (TypeError, ValueError): errors.append(f"invalid_step:{index}")
            ids.append(step.get("step_id"))
        if len(ids) != len(set(ids)): errors.append("duplicate_step")
        known = set(ids)
        if any(dep not in known for step in steps if isinstance(step, Mapping) for dep in step.get("dependency_step_ids", [])): errors.append("missing_dependency")
        graph = {step.get("step_id"): step.get("dependency_step_ids", []) for step in steps if isinstance(step, Mapping)}
        visiting, visited = set(), set()
        def cycle(node: Any) -> bool:
            if node in visiting: return True
            if node in visited: return False
            visiting.add(node)
            if any(cycle(dep) for dep in graph.get(node, []) if dep in graph): return True
            visiting.remove(node); visited.add(node); return False
        if any(cycle(node) for node in list(graph)): errors.append("circular_dependency")
    reasons = value.get("blocked_reasons")
    if not isinstance(reasons, list) or any(not isinstance(x, Mapping) or x.get("code") not in BLOCK_REASONS for x in reasons): errors.append("invalid_blocked_reasons")
    if value.get("readiness") in {"ready", "partial"} and reasons: errors.append("readiness_reason_mismatch")
    if isinstance(reasons, list) and isinstance(value.get("unresolved_requirements"), list):
        expected_unresolved = sorted({x.get("domain", x.get("link", x.get("scope", "unknown"))) for x in reasons if isinstance(x, Mapping)})
        if expected_unresolved != value["unresolved_requirements"]: errors.append("unresolved_consistency_mismatch")
    for key in ("warnings", "unresolved_requirements", "expected_outputs"):
        if not isinstance(value.get(key), list): errors.append(f"invalid_{key}")
    if _unsafe(value): errors.append("sensitive_or_unsafe_value")
    try: json.dumps(value, allow_nan=False)
    except (TypeError, ValueError): errors.append("not_json_serializable")
    if not required - set(value):
        try:
            fingerprint = compute_plan_fingerprint(value)
            if value.get("fingerprint") != fingerprint: errors.append("fingerprint_mismatch")
            if value.get("plan_id") != "capability-bootstrap-plan-" + fingerprint[:24]: errors.append("plan_id_mismatch")
        except (TypeError, ValueError): pass
    return BootstrapPlanValidationResult(not errors, tuple(errors))


__all__ = ["BootstrapPlanValidationResult", "validate_capability_bootstrap_plan"]
