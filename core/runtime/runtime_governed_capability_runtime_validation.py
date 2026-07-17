from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

INPUT_CONTRACT = "zero.runtime.governed_capability_runtime_input.v1"
STATE_CONTRACT = "zero.runtime.governed_capability_runtime_state.v1"
RESULT_CONTRACT = "zero.runtime.governed_capability_runtime_result.v1"
SCHEMA_VERSION = "1"
STAGES = (
    "capability_ready", "activation_ready", "execution_request_ready",
    "dry_run_bridge_closed", "observation_closed", "decision_readiness_closed",
    "decision_authorization_closed", "transaction_prepared", "runtime_closed",
)
STAGE_STATUSES = frozenset({"pending", "running", "completed", "blocked", "failed", "invalid", "skipped"})
PERMISSIONS = (
    "filesystem_write", "filesystem_mutation", "external_process", "network",
    "model_invocation", "transaction_commit",
)
CLAIMS = (
    "execution_started_claim", "execution_completion_claim",
    "mutation_authorization_claim", "mutation_performed_claim",
    "transaction_committed_claim",
)
INPUT_FIELDS = frozenset({"contract", "schema_version", "upstream_artifacts", "explicit_inputs", "runtime_options"})
UPSTREAM_FIELDS = frozenset({
    "resume_from",
    "capability_profile", "capability_strategy", "activation_verification_closure",
    "execution_authority", "execution_request", "dry_run_bridge_closure",
    "observation_evidence_closure", "decision_readiness_closure", "decision_authorization_closure",
})
RESUME_POINTS = frozenset({None, "decision_readiness_closed", "decision_authorization_closed", "transaction_preparation_input_ready"})
EXPLICIT_FIELDS = frozenset({
    "workspace_root", "observation_kind", "relative_target", "observation_limits",
    "decision_question", "decision_proposal", "requested_scope",
    "requested_effect_class", "requested_permissions", "sufficiency_requirements",
    "execution_intent", "proposal", "approval_record", "admission_record",
    "operator_review", "operator_execution_request", "active_authorization_request", "now",
})
OPTION_FIELDS = frozenset({"stop_after_stage", "allow_read_only_observation", "require_full_validation", "dry_run_only"})


@dataclass(frozen=True)
class RuntimeValidationResult:
    valid: bool
    errors: tuple[str, ...]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def detached_json_value(value: Any) -> Any:
    return json.loads(canonical_json(value))


def validate_governed_capability_runtime_input(value: Any) -> RuntimeValidationResult:
    errors: list[str] = []
    if not isinstance(value, Mapping):
        return RuntimeValidationResult(False, ("input_not_object",))
    if set(value) != INPUT_FIELDS or value.get("contract") != INPUT_CONTRACT or value.get("schema_version") != SCHEMA_VERSION:
        errors.append("invalid_input_contract")
    upstream = value.get("upstream_artifacts")
    explicit = value.get("explicit_inputs")
    options = value.get("runtime_options")
    if not isinstance(upstream, Mapping) or set(upstream) != UPSTREAM_FIELDS:
        errors.append("invalid_upstream_artifacts")
    elif upstream.get("resume_from") not in RESUME_POINTS:
        errors.append("invalid_stage_injection_order")
    elif upstream.get("resume_from") is None and any(upstream.get(k) is not None for k in (
            "observation_evidence_closure", "decision_readiness_closure", "decision_authorization_closure")):
        errors.append("unexpected_stage_injection")
    elif upstream.get("resume_from") == "decision_readiness_closed" and (
            upstream.get("decision_readiness_closure") is None or upstream.get("decision_authorization_closure") is not None):
        errors.append("invalid_readiness_injection")
    elif upstream.get("resume_from") in {"decision_authorization_closed", "transaction_preparation_input_ready"} and upstream.get("decision_authorization_closure") is None:
        errors.append("invalid_authorization_injection")
    if not isinstance(explicit, Mapping) or set(explicit) != EXPLICIT_FIELDS:
        errors.append("missing_explicit_caller_input")
    if not isinstance(options, Mapping) or set(options) != OPTION_FIELDS:
        errors.append("invalid_runtime_options")
    elif (options.get("dry_run_only") is not True
          or options.get("allow_read_only_observation") is not True
          or options.get("require_full_validation") is not True
          or options.get("stop_after_stage") not in (*STAGES, None)):
        errors.append("unsafe_runtime_option")
    try:
        detached_json_value(value)
    except (TypeError, ValueError, OverflowError):
        errors.append("input_not_json_safe")
    return RuntimeValidationResult(not errors, tuple(dict.fromkeys(errors)))


def validate_governed_capability_runtime_state(value: Any) -> RuntimeValidationResult:
    if not isinstance(value, Mapping):
        return RuntimeValidationResult(False, ("state_not_object",))
    errors: list[str] = []
    if value.get("contract") != STATE_CONTRACT or value.get("schema_version") != SCHEMA_VERSION:
        errors.append("invalid_state_contract")
    states = value.get("stage_states")
    if value.get("stage_order") != list(STAGES) or not isinstance(states, Mapping) or set(states) != set(STAGES):
        errors.append("invalid_stage_registry")
    elif any(not isinstance(s, Mapping) or s.get("status") not in STAGE_STATUSES for s in states.values()):
        errors.append("unknown_stage_status")
    permissions = value.get("permissions")
    if not isinstance(permissions, Mapping) or set(permissions) != set(PERMISSIONS) or any(v is not False for v in permissions.values()):
        errors.append("permission_invariant_violation")
    if any(value.get(name) is not False for name in CLAIMS):
        errors.append("claim_invariant_violation")
    if value.get("dry_run_only") is not True:
        errors.append("dry_run_invariant_violation")
    expected = fingerprint({k: v for k, v in value.items() if k not in {"runtime_id", "runtime_fingerprint"}})
    if value.get("runtime_fingerprint") != expected or value.get("runtime_id") != "governed-capability-runtime-" + expected[:24]:
        errors.append("state_identity_mismatch")
    return RuntimeValidationResult(not errors, tuple(dict.fromkeys(errors)))
