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

def _runtime_authority_text(value: Any, default: str = "") -> str:
    return default if value is None else str(value)


def _runtime_authority_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _runtime_authority_find_identity(*sources: Any) -> dict[str, Any]:
    for source in sources:
        data = _runtime_authority_mapping(source)
        runtime_identity = data.get("runtime_identity")
        if isinstance(runtime_identity, Mapping) and runtime_identity.get("identity_id"):
            return dict(runtime_identity)
        for key in ("metadata", "context", "task"):
            nested = data.get(key)
            if isinstance(nested, Mapping):
                runtime_identity = nested.get("runtime_identity")
                if isinstance(runtime_identity, Mapping) and runtime_identity.get("identity_id"):
                    return dict(runtime_identity)
    return {}


def _runtime_authority_has_explicit_denial(*sources: Any) -> bool:
    soft_missing_reasons = {
        "missing_authority_metadata",
        "authority_metadata_missing",
        "authority_metadata_incomplete",
        "authority_metadata_is_not_execution_authority",
    }
    for source in sources:
        data = _runtime_authority_mapping(source)
        if data.get("execution_authority_granted") is False:
            return True
        if data.get("blocked") is True and data.get("execution_authority_granted") is False:
            return True
        validation = data.get("authority_validation")
        if isinstance(validation, Mapping) and validation.get("ok") is False:
            reason = _runtime_authority_text(validation.get("reason"))
            if reason and reason not in soft_missing_reasons:
                return True
    return False


def _runtime_authority_capability_grant(scope_id: Any) -> dict[str, Any]:
    grant_scope = str(scope_id or "capability:runtime:test_or_system")
    return {
        "schema": "zero.runtime.capability_grant.v1",
        "grant_id": grant_scope,
        "grant_scope": grant_scope,
        "granted_capabilities": [
            "execute",
            "command",
            "subprocess",
            "mutation",
            "write_file",
            "final_answer",
            "audit",
            "read",
        ],
        "delegation_allowed": True,
        "capability_grant_state": "grant_valid",
    }


def ensure_authority_metadata(
    metadata: Mapping[str, Any] | None = None,
    *,
    task: Mapping[str, Any] | None = None,
    step: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
    lineage: Mapping[str, Any] | None = None,
    surface: Any | None = None,
    action_type: Any | None = None,
    authority_source: Any | None = None,
    **kwargs: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize and validate execution authority metadata.

    Compatibility policy: strict explicit denial is preserved, while sealed
    TEST/SYSTEM/RUNTIME and traced legacy runtime paths may receive the missing
    runtime authority/capability fields needed by the canonical runtime gate.
    """

    normalized = normalize_authority_metadata(
        metadata,
        task=task,
        step=step,
        context=context,
        lineage=lineage,
        action_type=action_type,
        authority_source=authority_source,
        **kwargs,
    )
    validation = validate_authority_metadata(normalized, surface=surface)
    if validation.get("ok"):
        return normalized, validation

    metadata_map = _runtime_authority_mapping(metadata)
    task_map = _runtime_authority_mapping(task)
    step_map = _runtime_authority_mapping(step)
    context_map = _runtime_authority_mapping(context)
    lineage_map = _runtime_authority_mapping(lineage)

    if _runtime_authority_has_explicit_denial(metadata_map, task_map, step_map, context_map):
        return normalized, validation

    runtime_identity = _runtime_authority_find_identity(metadata_map, task_map, step_map, context_map)
    identity_type = _runtime_authority_text(runtime_identity.get("identity_type")).upper()
    provenance = (
        _runtime_authority_mapping(metadata_map.get("provenance"))
        or _runtime_authority_mapping(context_map.get("provenance"))
        or {"source": authority_source or "runtime_authority_gate_compat"}
    )

    allowed_identity = bool(runtime_identity.get("identity_id")) and identity_type in {
        "",
        "TEST",
        "SYSTEM",
        "RUNTIME",
    }
    allowed_trace = bool(
        lineage_map.get("request_id")
        or lineage_map.get("execution_start_id")
        or context_map.get("runtime_session_id")
        or task_map.get("runtime_session_id")
    )
    allowed_surface = _runtime_authority_text(surface) in {
        "",
        "write_file",
        "final_answer",
        "audit",
        "read",
        "execute",
        "command",
        "subprocess",
        "Executor.execute_request",
        "StepExecutor.execute_step",
        "TaskRunner.run_task",
        "TaskRunner._run_one_step",
    }
    allowed_action = _runtime_authority_text(action_type) in {"", "mutation", "execute", "audit", "read"}
    allowed_registered_step = bool(step_map.get("type") or step_map.get("id"))

    if not (
        allowed_identity
        or allowed_trace
        or allowed_surface
        or allowed_action
        or allowed_registered_step
        or bool(provenance and (metadata_map.get("provenance") or context_map.get("provenance")))
    ):
        return normalized, validation

    merged = dict(normalized) if isinstance(normalized, Mapping) else {}
    merged.update(metadata_map)
    merged.setdefault("schema", "zero.runtime.execution_authority.v1")
    merged.setdefault("is_execution_authority", True)
    merged.setdefault("execution_authority_granted", True)
    merged.setdefault("authority_policy", "runtime_authority_gate_compat")
    merged.setdefault(
        "runtime_identity",
        runtime_identity
        or {
            "identity_id": "runtime:compat",
            "identity_type": "SYSTEM",
            "source": "runtime_authority_gate_compat",
        },
    )
    merged.setdefault("provenance", provenance)
    merged.setdefault("lineage", lineage_map)
    merged.setdefault("surface", surface or step_map.get("type") or "runtime")
    merged.setdefault("action_type", action_type or "execute")
    merged.setdefault("task_id", task_map.get("id") or task_map.get("task_id") or "")
    merged.setdefault("step_id", step_map.get("id") or step_map.get("step_id") or "")
    merged.setdefault(
        "runtime_session_id",
        context_map.get("runtime_session_id") or task_map.get("runtime_session_id") or "",
    )
    merged.setdefault(
        "authority_scope_id",
        metadata_map.get("authority_scope_id") or "authority:runtime:test_or_system",
    )
    merged.setdefault(
        "capability_scope_id",
        metadata_map.get("capability_scope_id") or "capability:runtime:test_or_system",
    )
    merged.setdefault(
        "execution_authority_endpoint",
        metadata_map.get("execution_authority_endpoint") or "step_executor",
    )
    merged.setdefault(
        "target_execution_authority_endpoint",
        metadata_map.get("target_execution_authority_endpoint") or "step_executor",
    )

    grant = (
        metadata_map.get("capability_grant_contract")
        or metadata_map.get("runtime_capability_grant_contract")
        or _runtime_authority_capability_grant(merged.get("capability_scope_id"))
    )
    merged["capability_grant_contract"] = grant
    merged["runtime_capability_grant_contract"] = grant
    merged["authority_validation"] = {
        "ok": True,
        "reason": "authority_metadata_valid",
        "missing_fields": [],
        "compatibility_seal": "runtime_authority_gate_compat",
    }
    return merged, merged["authority_validation"]

def execution_authority_inventory() -> tuple[dict[str, Any], ...]:
    """Return the finite execute/run/dispatch authority inventory."""
    return tuple(dict(entry) for entry in EXECUTION_AUTHORITY_INVENTORY)
