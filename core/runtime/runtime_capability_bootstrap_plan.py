from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_detection_validation import validate_capability_detection
from core.runtime.runtime_capability_provider_discovery_validation import validate_capability_provider_discovery
from core.runtime.runtime_capability_registry_validation import validate_capability_registry
from core.runtime.runtime_capability_strategy_validation import MODES, validate_capability_strategy
from core.runtime.runtime_capability_validation import validate_capability_profile


SCHEMA = "zero.runtime.capability_bootstrap_plan.v1"
POLICY_SCHEMA = "zero.runtime.capability_bootstrap_policy.v1"
SCOPES = frozenset({"capability_runtime_initialization", "capability_profile_activation", "capability_strategy_activation", "provider_binding_validation", "offline_safe_runtime_preparation"})
READINESS = frozenset({"ready", "partial", "blocked", "invalid", "unsupported"})
STEP_TYPES = ("validate_discovery", "validate_detection", "validate_profile", "validate_strategy", "validate_registry", "verify_provider_bindings", "verify_required_domains", "prepare_runtime_capability_context", "prepare_strategy_context", "seal_bootstrap_inputs", "handoff_to_bootstrap_executor")
OWNERS = frozenset({"planning", "validation", "detection", "profile", "strategy", "registry", "bootstrap_executor"})
BLOCK_REASONS = frozenset({"invalid_artifact", "linkage_mismatch", "required_provider_unbound", "required_domain_unavailable", "required_detection_failed", "strategy_incompatible", "safety_constraint_unsatisfied", "unsupported_scope", "unsupported_strategy"})
_IDENTITY_EXCLUDED = frozenset({"plan_id", "fingerprint", "planned_at"})
_SENSITIVE = frozenset({"username", "hostname", "home", "path", "environment", "environment_values", "api_key", "token", "access_token", "credential", "credentials", "executable", "exception", "traceback", "command", "callable", "provider_instance", "module", "class"})


class BootstrapPlanError(ValueError):
    def __init__(self, code: str) -> None: super().__init__(code); self.code = code


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unsafe(value: Any) -> bool:
    if isinstance(value, Mapping): return any(str(k).casefold() in _SENSITIVE or _unsafe(v) for k, v in value.items())
    if isinstance(value, (list, tuple)): return any(_unsafe(v) for v in value)
    if not isinstance(value, (str, int, float, bool, type(None))): return True
    return isinstance(value, str) and ("object at 0x" in value.casefold() or "traceback (most recent" in value.casefold())


def default_policy() -> dict[str, Any]:
    return normalize_policy({"required_domains": ["cpu"], "optional_domains": ["accelerator", "memory", "storage", "tools"], "allow_partial_detection": True, "require_all_selected_providers_bound": False, "offline_only": True, "allow_unsupported_optional_domains": True, "maximum_step_count": len(STEP_TYPES), "allowed_bootstrap_scopes": sorted(SCOPES), "allowed_strategy_modes": sorted(MODES)})


def compute_policy_fingerprint(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json({k: deepcopy(v) for k, v in value.items() if k != "fingerprint"}).encode()).hexdigest()


def normalize_policy(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"required_domains", "optional_domains", "allow_partial_detection", "require_all_selected_providers_bound", "offline_only", "allow_unsupported_optional_domains", "maximum_step_count", "allowed_bootstrap_scopes", "allowed_strategy_modes"}
    if not isinstance(value, Mapping) or set(value) - required - {"schema", "fingerprint"}: raise BootstrapPlanError("malformed_policy")
    result = deepcopy(dict(value)); result["schema"] = POLICY_SCHEMA
    for key in ("required_domains", "optional_domains", "allowed_bootstrap_scopes", "allowed_strategy_modes"):
        if not isinstance(result.get(key), list) or any(not isinstance(x, str) for x in result[key]): raise BootstrapPlanError("malformed_policy")
        result[key] = sorted(set(result[key]))
    if set(result["required_domains"]) & set(result["optional_domains"]): raise BootstrapPlanError("malformed_policy")
    if any(not isinstance(result.get(k), bool) for k in ("allow_partial_detection", "require_all_selected_providers_bound", "offline_only", "allow_unsupported_optional_domains")): raise BootstrapPlanError("malformed_policy")
    if isinstance(result.get("maximum_step_count"), bool) or not isinstance(result.get("maximum_step_count"), int) or not 1 <= result["maximum_step_count"] <= 64: raise BootstrapPlanError("malformed_policy")
    if not set(result["allowed_bootstrap_scopes"]) <= SCOPES or not set(result["allowed_strategy_modes"]) <= MODES or _unsafe(result): raise BootstrapPlanError("malformed_policy")
    supplied = result.pop("fingerprint", None); result["fingerprint"] = compute_policy_fingerprint(result)
    if supplied is not None and supplied != result["fingerprint"]: raise BootstrapPlanError("malformed_policy")
    return json.loads(canonical_json(result))


def compute_step_fingerprint(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json({k: deepcopy(v) for k, v in value.items() if k not in {"step_id", "fingerprint"}}).encode()).hexdigest()


def _step(order: int, step_type: str, dependency_ids: list[str], linkage: Mapping[str, Any], *, owner: str = "planning", blocked_reason: str | None = None) -> dict[str, Any]:
    base = {"step_type": step_type, "order": order, "dependency_step_ids": sorted(dependency_ids), "input_artifact_references": deepcopy(dict(linkage)), "expected_output_type": f"symbolic_{step_type}_result", "required": True, "execution_ownership": owner, "authorization_requirement": "future_explicit_executor_authorization" if owner == "bootstrap_executor" else "none", "mutation_classification": "future_mutation" if owner == "bootstrap_executor" else "read_only", "status": "blocked" if blocked_reason else "planned", "blocked_reason": blocked_reason, "metadata": {}}
    fp = compute_step_fingerprint(base)
    return {**base, "fingerprint": fp, "step_id": "bootstrap-step-" + fp[:24]}


def compute_plan_fingerprint(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json({k: deepcopy(v) for k, v in value.items() if k not in _IDENTITY_EXCLUDED}).encode()).hexdigest()


def _link(artifact: Mapping[str, Any] | None, id_key: str) -> dict[str, Any] | None:
    if artifact is None: return None
    return {"schema": artifact.get("schema"), "artifact_id": artifact.get(id_key), "fingerprint": artifact.get("fingerprint")}


def plan_capability_bootstrap(*, discovery: Mapping[str, Any], detection: Mapping[str, Any], profile: Mapping[str, Any], strategy: Mapping[str, Any], provenance: Mapping[str, Any], registry: Mapping[str, Any] | None = None, scope: str = "capability_runtime_initialization", policy: Mapping[str, Any] | None = None, planned_at: str | None = None) -> dict[str, Any]:
    try: normalized_policy = normalize_policy(policy or {k: v for k, v in default_policy().items() if k not in {"schema", "fingerprint"}})
    except BootstrapPlanError: normalized_policy = {"schema": POLICY_SCHEMA, "fingerprint": "invalid", "malformed": True}
    linkage = {"discovery": _link(discovery, "discovery_id"), "detection": _link(detection, "detection_id"), "profile": _link(profile, "profile_id"), "strategy": _link(strategy, "strategy_id"), "registry": _link(registry, "registry_id")}
    errors, blocked, warnings = [], [], []
    validators = (("discovery", validate_capability_provider_discovery, discovery), ("detection", validate_capability_detection, detection), ("profile", validate_capability_profile, profile), ("strategy", validate_capability_strategy, strategy))
    if registry is not None: validators += (("registry", validate_capability_registry, registry),)
    for name, validator, artifact in validators:
        result = validator(artifact)
        if not result.valid: errors.append({"code": "invalid_artifact", "artifact": name})
    if normalized_policy.get("malformed"): errors.append({"code": "invalid_artifact", "artifact": "policy"})
    if scope not in SCOPES or scope not in normalized_policy.get("allowed_bootstrap_scopes", []): blocked.append({"code": "unsupported_scope", "scope": scope})
    detection_source = detection.get("source", {}) if isinstance(detection, Mapping) else {}
    expected = {"discovery_id": discovery.get("discovery_id"), "discovery_fingerprint": discovery.get("fingerprint"), "detection_id": detection.get("detection_id"), "detection_fingerprint": detection.get("fingerprint")}
    if detection_source.get("discovery_id") != expected["discovery_id"] or detection_source.get("discovery_fingerprint") != expected["discovery_fingerprint"]: blocked.append({"code": "linkage_mismatch", "link": "discovery_detection"})
    if provenance.get("profile_detection_id") != expected["detection_id"] or provenance.get("profile_detection_fingerprint") != expected["detection_fingerprint"]: blocked.append({"code": "linkage_mismatch", "link": "detection_profile"})
    if strategy.get("profile_id") != profile.get("profile_id") or strategy.get("profile_fingerprint") != profile.get("fingerprint"): blocked.append({"code": "linkage_mismatch", "link": "profile_strategy"})
    if registry is not None and (provenance.get("registry_id") != registry.get("registry_id") or provenance.get("registry_fingerprint") != registry.get("fingerprint")): blocked.append({"code": "linkage_mismatch", "link": "registry_planning"})
    mode = strategy.get("recommended_mode")
    if mode not in normalized_policy.get("allowed_strategy_modes", []): blocked.append({"code": "unsupported_strategy", "mode": mode})
    results = {item.get("domain"): item for item in detection.get("results", []) if isinstance(item, Mapping)}
    required_domains = normalized_policy.get("required_domains", [])
    optional_domains = normalized_policy.get("optional_domains", [])
    for domain in required_domains:
        result = results.get(domain)
        if result is not None and result.get("status") == "failed": blocked.append({"code": "required_detection_failed", "domain": domain})
        elif result is None or result.get("status") not in {"available", "partial"}: blocked.append({"code": "required_domain_unavailable", "domain": domain})
    for domain in optional_domains:
        result = results.get(domain)
        if result is None or result.get("status") != "available": warnings.append({"code": "optional_domain_unavailable", "domain": domain})
    for selected in discovery.get("selected_providers", []):
        if selected.get("binding_status") == "unbound":
            target = blocked if selected.get("domain") in required_domains or normalized_policy.get("require_all_selected_providers_bound") else warnings
            target.append({"code": "required_provider_unbound" if target is blocked else "optional_provider_unbound", "domain": selected.get("domain"), "provider_id": selected.get("provider_id")})
    accelerator = results.get("accelerator", {})
    if mode == "accelerator_available" and accelerator.get("status") != "available": blocked.append({"code": "strategy_incompatible", "mode": mode})
    if mode == "cpu_only" and strategy.get("execution_preferences", {}).get("preferred_compute") == "accelerator": blocked.append({"code": "strategy_incompatible", "mode": mode})
    blocked.sort(key=canonical_json); warnings.sort(key=canonical_json); errors.sort(key=canonical_json)
    readiness = "invalid" if errors else "unsupported" if any(x["code"].startswith("unsupported") for x in blocked) else "blocked" if blocked else "partial" if warnings else "ready"
    step_types = [x for x in STEP_TYPES if registry is not None or x != "validate_registry"]
    if mode == "cpu_only": step_types = [x for x in step_types if "accelerator" not in x]
    if normalized_policy.get("offline_only"): step_types = [x for x in step_types if "network" not in x]
    step_types = step_types[:normalized_policy.get("maximum_step_count", len(step_types))]
    steps, dependencies = [], []
    first_block = blocked[0]["code"] if blocked else "invalid_artifact" if errors else None
    for order, step_type in enumerate(step_types):
        owner = "bootstrap_executor" if step_type == "handoff_to_bootstrap_executor" else "validation" if step_type.startswith("validate_") or step_type.startswith("verify_") else "planning"
        step = _step(order, step_type, dependencies[-1:] if dependencies else [], {k: v for k, v in linkage.items() if v is not None}, owner=owner, blocked_reason=first_block if first_block and step_type == "handoff_to_bootstrap_executor" else None)
        steps.append(step); dependencies.append(step["step_id"])
    unresolved = sorted({x.get("domain", x.get("link", x.get("scope", "unknown"))) for x in blocked})
    base = {"schema": SCHEMA, "readiness": readiness, "source_artifact_linkage": linkage, "requested_bootstrap_scope": scope, "ordered_steps": steps, "blocked_reasons": blocked + errors, "warnings": warnings, "unresolved_requirements": unresolved, "policy_constraints": normalized_policy, "safety_constraints": {"offline_only": bool(normalized_policy.get("offline_only")), "execution_prohibited": True, "mutation_prohibited": True}, "expected_outputs": ["sealed_bootstrap_inputs", "future_executor_handoff_metadata"], "planning_metadata": {"kind": "read_only_deterministic_planning"}, "planned_at": planned_at}
    fp = compute_plan_fingerprint(base)
    return json.loads(canonical_json({**base, "fingerprint": fp, "plan_id": "capability-bootstrap-plan-" + fp[:24]}))


def executor_handoff_metadata(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {"plan_id": plan.get("plan_id"), "plan_fingerprint": plan.get("fingerprint"), "readiness": plan.get("readiness"), "scope": plan.get("requested_bootstrap_scope"), "execution_performed": False}


__all__ = ["SCHEMA", "POLICY_SCHEMA", "SCOPES", "READINESS", "STEP_TYPES", "OWNERS", "BLOCK_REASONS", "BootstrapPlanError", "canonical_json", "default_policy", "normalize_policy", "compute_policy_fingerprint", "compute_step_fingerprint", "compute_plan_fingerprint", "plan_capability_bootstrap", "executor_handoff_metadata"]
