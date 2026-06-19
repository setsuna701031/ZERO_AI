from __future__ import annotations

import hashlib
from typing import Any, Mapping

from core.runtime.runtime_surface_registry import classify_runtime_surface


REQUIRED_AUTHORITY_METADATA_FIELDS = (
    "task_id",
    "step_id",
    "authority_source",
    "runtime_session",
    "approval_state",
    "policy_result",
    "trace_id",
)

ALLOWED_APPROVAL_STATES = {"approved", "allowed", "preapproved"}

EXECUTION_AUTHORITY_INVENTORY = (
    {"surface": "RuntimeDispatcher.dispatch", "role": "ISSUER", "execute": False, "gate_required": False, "capability_required": False},
    {"surface": "TaskRunner.run_task", "role": "DELEGATE", "execute": False, "gate_required": True, "capability_required": True},
    {"surface": "TaskRunner._run_one_step", "role": "DELEGATE", "execute": False, "gate_required": True, "capability_required": True},
    {"surface": "TaskRuntime.readonly_command_gate", "role": "DISPATCH", "execute": False, "gate_required": True, "capability_required": False},
    {"surface": "StepExecutor.execute_step", "role": "EXECUTE", "execute": True, "gate_required": True, "capability_required": True},
    {"surface": "execution_gateway.safe_subprocess_run", "role": "EXECUTE", "execute": True, "gate_required": True, "capability_required": False},
    {"surface": "Executor.execute_request", "role": "EXECUTE", "execute": True, "gate_required": True, "capability_required": False},
    {"surface": "runtime_native_execution_path", "role": "DESCRIBE", "execute": False, "gate_required": False, "capability_required": False},
)


def validate_authority_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    surface: Any | None = None,
) -> dict[str, Any]:
    def _with_invariant(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            from core.runtime.runtime_constitution_freeze import (
                RuntimeInvariant,
                record_runtime_invariant_violation,
            )

            classified_surface = classify_runtime_surface(surface)
            invariant = (
                RuntimeInvariant.AUTHORITY_SIDE_EFFECT_REQUIRES_AUTHORITY
                if classified_surface.side_effect
                else RuntimeInvariant.AUTHORITY_CONTEXT_IS_NOT_AUTHORITY
            )
            violation = record_runtime_invariant_violation(
                invariant,
                component="authority",
                reason=str(payload.get("reason") or "authority_metadata_invalid"),
                context={"surface": classified_surface.name, "missing_fields": payload.get("missing_fields", [])},
            )
            payload = {**payload, "invariant_violations": [violation.to_dict()]}
        except Exception:
            pass
        return payload

    if surface is not None:
        classified = classify_runtime_surface(surface)
        if not classified.requires_authority:
            return {
                "ok": True,
                "reason": "authority_not_required_for_surface",
                "missing_fields": [],
                "surface": classified.name,
                "requires_authority": False,
            }

    payload = dict(metadata or {})
    if payload.get("descriptive_only") or payload.get("compatibility_authority_adapter"):
        return _with_invariant({
            "ok": False,
            "reason": "authority_metadata_is_not_execution_authority",
            "missing_fields": [],
        })
    missing = [
        key
        for key in REQUIRED_AUTHORITY_METADATA_FIELDS
        if payload.get(key) in (None, "", {})
    ]
    approval_state = str(payload.get("approval_state") or "").strip().lower()
    policy_result = payload.get("policy_result")
    policy_allowed = False
    if isinstance(policy_result, Mapping):
        policy_allowed = bool(
            policy_result.get("allowed")
            or policy_result.get("allow")
            or str(policy_result.get("decision") or "").strip().lower()
            in {"allow", "allowed"}
        )
    elif isinstance(policy_result, bool):
        policy_allowed = policy_result

    if missing:
        return _with_invariant({
            "ok": False,
            "reason": "missing_authority_metadata",
            "missing_fields": missing,
        })
    if approval_state not in ALLOWED_APPROVAL_STATES:
        return _with_invariant({
            "ok": False,
            "reason": "approval_state_not_allowed",
            "approval_state": approval_state,
        })
    if not policy_allowed:
        return _with_invariant({
            "ok": False,
            "reason": "policy_result_not_allowed",
            "policy_result": policy_result,
        })
    return {
        "ok": True,
        "reason": "authority_metadata_valid",
        "missing_fields": [],
    }


def _stable_authority_id(prefix: str, *parts: Any) -> str:
    raw = repr(parts).encode("utf-8", errors="replace")
    return f"{prefix}:{hashlib.sha256(raw).hexdigest()[:16]}"


def _first_mapping(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def normalize_authority_metadata(
    metadata: Mapping[str, Any] | None = None,
    *,
    task: Mapping[str, Any] | None = None,
    step: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
    lineage: Mapping[str, Any] | None = None,
    authority_source: str = "runtime_compatibility",
    action_type: str = "execute",
) -> dict[str, Any]:
    payload = dict(metadata or {})
    task_payload = dict(task or {})
    step_payload = dict(step or {})
    context_payload = dict(context or {})
    lineage_payload = dict(lineage or {})
    review_only_context_keys = {
        "governance_snapshot",
        "constitution",
        "enforce_legality",
        "runtime_freeze",
        "freeze_state",
        "runtime_frozen",
        "enforce_freeze",
        "policy_check",
        "policy_context",
        "review_context",
        "governance_context",
        "policy_result",
        "replay_context",
        "replay_source",
        "replay_run_id",
        "source_trace_id",
        "source_transaction_ids",
        "recovery_context",
        "recovery_source",
        "recovery_attempt_id",
        "original_transaction_id",
        "rollback_evidence",
        "evidence",
        "canonical_evidence",
        "evidence_snapshot",
        "evidence_refs",
        "operator_context",
        "operator_run_id",
        "operator_repo_scan",
        "operator_edit_plan",
        "operator_prediction",
    }
    has_explicit_authority = bool(
        payload.get("execution_authority")
        or payload.get("authority_metadata")
        or payload.get("execution_authority_metadata")
        or payload.get("authority_source")
    )
    if (
        context_payload
        and set(context_payload).issubset(review_only_context_keys)
        and not payload
        and not has_explicit_authority
    ):
        return payload

    runtime_identity = _first_mapping(
        payload.get("runtime_identity"),
        context_payload.get("runtime_identity"),
        task_payload.get("runtime_identity"),
    )
    policy_result = payload.get("policy_result")
    if not isinstance(policy_result, Mapping) and policy_result is not True:
        policy_result = _first_mapping(
            payload.get("policy"),
            context_payload.get("policy_result"),
            task_payload.get("policy_result"),
        )

    task_id = _first_text(
        payload.get("task_id"),
        task_payload.get("task_id"),
        task_payload.get("id"),
        task_payload.get("task_name"),
        context_payload.get("task_id"),
        lineage_payload.get("task_id"),
        lineage_payload.get("request_id"),
    )
    step_id = _first_text(
        payload.get("step_id"),
        step_payload.get("step_id"),
        step_payload.get("id"),
        context_payload.get("step_id"),
        lineage_payload.get("step_id"),
    )
    runtime_session = _first_text(
        payload.get("runtime_session"),
        context_payload.get("runtime_session"),
        context_payload.get("runtime_session_id"),
        task_payload.get("runtime_session"),
        task_payload.get("runtime_session_id"),
        lineage_payload.get("execution_start_id"),
        lineage_payload.get("request_id"),
    )
    trace_id = _first_text(
        payload.get("trace_id"),
        context_payload.get("trace_id"),
        task_payload.get("trace_id"),
        lineage_payload.get("trace_id"),
        lineage_payload.get("request_id"),
        lineage_payload.get("execution_start_id"),
    )

    has_runtime_context = bool(
        task_payload
        or context_payload
        or lineage_payload
        or runtime_identity
        or payload.get("controlled_runtime_execution_boundary")
        or payload.get("controlled_runtime_execution_boundary_report")
        or payload.get("governed_action_gateway_report")
    )
    has_step_context = bool(step_payload or payload.get("command") or lineage_payload.get("request_id"))
    if not (has_runtime_context and has_step_context):
        return payload

    if not task_id:
        task_id = _stable_authority_id(
            "legacy_task",
            runtime_identity,
            lineage_payload,
            task_payload,
            payload.get("command"),
        )
    if not step_id:
        step_id = _stable_authority_id(
            "legacy_step",
            step_payload,
            payload.get("command"),
            lineage_payload.get("request_id"),
        )
    if not runtime_session:
        runtime_session = _stable_authority_id(
            "runtime_session",
            task_id,
            runtime_identity,
            lineage_payload,
        )
    if not trace_id:
        trace_id = _stable_authority_id("trace", task_id, step_id, runtime_session)

    normalized = {
        **payload,
        "task_id": task_id,
        "step_id": step_id,
        "authority_source": _first_text(payload.get("authority_source"), authority_source),
        "runtime_session": runtime_session,
        "approval_state": _first_text(payload.get("approval_state")),
        "policy_result": policy_result,
        "trace_id": trace_id,
        "authority_status": _first_text(payload.get("authority_status"), payload.get("status"), "allowed"),
        "action_type": _first_text(payload.get("action_type"), action_type),
        "compatibility_authority_adapter": not has_explicit_authority,
        "descriptive_only": not has_explicit_authority,
    }
    return normalized


def ensure_authority_metadata(
    metadata: Mapping[str, Any] | None = None,
    *,
    surface: Any | None = None,
    **kwargs: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = normalize_authority_metadata(metadata, **kwargs)
    return normalized, validate_authority_metadata(normalized, surface=surface)


def execution_authority_inventory() -> tuple[dict[str, Any], ...]:
    """Return the finite execute/run/dispatch authority inventory."""
    return tuple(dict(entry) for entry in EXECUTION_AUTHORITY_INVENTORY)
