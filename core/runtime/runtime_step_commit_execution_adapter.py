from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_STEP_COMMIT_EXECUTION_ADAPTER_SCHEMA = (
    "zero.runtime.step_commit_execution_adapter.v1"
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _invocation_record_id(
    *,
    runtime_id: str | None,
    authority_record_id: str | None,
    commit_invocation_ready: bool,
    blocked_reason: str,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "authority_record_id": authority_record_id,
            "commit_invocation_ready": commit_invocation_ready,
            "blocked_reason": blocked_reason,
        }
    )
    return (
        "runtime-step-commit-invocation::"
        f"{runtime_id or 'missing-runtime'}::{fragment}"
    )


def build_runtime_step_commit_invocation_record(
    runtime_step_commit_authority_record: dict[str, Any] | None,
) -> dict[str, Any]:
    authority = _as_mapping(runtime_step_commit_authority_record)
    commit_invocation_ready = authority.get("commit_authorized") is True
    blocked_reason = "none" if commit_invocation_ready else (
        authority.get("denial_reason") or "commit_not_authorized"
    )
    invocation_record_id = _invocation_record_id(
        runtime_id=authority.get("runtime_id"),
        authority_record_id=authority.get("authority_record_id"),
        commit_invocation_ready=commit_invocation_ready,
        blocked_reason=blocked_reason,
    )

    return {
        "schema": RUNTIME_STEP_COMMIT_EXECUTION_ADAPTER_SCHEMA,
        "invocation_record_id": invocation_record_id,
        "runtime_id": authority.get("runtime_id"),
        "source_authority_record_id": authority.get("authority_record_id"),
        "source_step_result_commit_request_id": authority.get(
            "source_step_result_commit_request_id"
        ),
        "commit_authorized": commit_invocation_ready,
        "commit_invocation_ready": commit_invocation_ready,
        "blocked_reason": blocked_reason,
        "result_kind": authority.get("result_kind") or "noop",
        "summary": authority.get("summary") or authority.get("result_summary") or "",
        "result_summary": authority.get("result_summary")
        or authority.get("summary")
        or "",
        "failure_reason": authority.get("failure_reason") or "none",
        "recovery_required": authority.get("recovery_required") is True,
        "execution_lease_id": authority.get("execution_lease_id"),
        "capability_grant_id": authority.get("capability_grant_id"),
        "executor_binding_id": authority.get("executor_binding_id"),
        "commit_invocation_envelope_only": True,
        "committed": False,
        "progress_updated": False,
        "cursor_advanced": False,
        "executor_imported": False,
        "scheduler_imported": False,
        "step_result_commit_called": False,
        "progress_mutated": False,
        "loop_continued": False,
        "automatic_retry_performed": False,
        "thread_created": False,
    }


def build_runtime_step_commit_execution_adapter_audit_projection(
    invocation_record: dict[str, Any] | None,
) -> dict[str, Any]:
    record = _as_mapping(invocation_record)
    return {
        "projection": "runtime_step_commit_execution_adapter_audit",
        "projection_only": True,
        "invocation_record_id": record.get("invocation_record_id"),
        "runtime_id": record.get("runtime_id"),
        "source_authority_record_id": record.get("source_authority_record_id"),
        "commit_invocation_ready": record.get("commit_invocation_ready") is True,
        "result_kind": record.get("result_kind"),
        "summary": record.get("summary"),
        "failure_reason": record.get("failure_reason", "none"),
        "recovery_required": record.get("recovery_required") is True,
        "blocked_reason": record.get("blocked_reason", "not_evaluated"),
        "committed": False,
        "progress_updated": False,
        "cursor_advanced": False,
        "executor_imported": False,
        "scheduler_imported": False,
        "step_result_commit_called": False,
        "progress_mutated": False,
        "loop_continued": False,
        "automatic_retry_performed": False,
        "thread_created": False,
        "commit_invocation_envelope_only": True,
    }


def build_runtime_step_commit_execution_adapter_audit_record(
    runtime_step_commit_authority_record: dict[str, Any] | None,
) -> dict[str, Any]:
    invocation = build_runtime_step_commit_invocation_record(
        runtime_step_commit_authority_record
    )
    return {
        "audit_schema": RUNTIME_STEP_COMMIT_EXECUTION_ADAPTER_SCHEMA + ".audit",
        "decision": "reserved_runtime_step_commit_invocation_envelope_only",
        "runtime_step_commit_invocation_record": invocation,
        "audit_projection": build_runtime_step_commit_execution_adapter_audit_projection(
            invocation
        ),
        "committed": False,
        "progress_updated": False,
        "cursor_advanced": False,
        "executor_imported": False,
        "scheduler_imported": False,
        "step_result_commit_called": False,
        "progress_mutated": False,
        "loop_continued": False,
        "automatic_retry_performed": False,
        "thread_created": False,
    }


def build_runtime_step_commit_execution_adapter_milestone_seal(
    runtime_step_commit_authority_record: dict[str, Any] | None,
) -> dict[str, Any]:
    audit = build_runtime_step_commit_execution_adapter_audit_record(
        runtime_step_commit_authority_record
    )
    invocation = _as_mapping(audit.get("runtime_step_commit_invocation_record"))
    return {
        "seal": "runtime_step_commit_execution_adapter_bundle",
        "schema": RUNTIME_STEP_COMMIT_EXECUTION_ADAPTER_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_STEP_COMMIT_INVOCATION_ENVELOPES_ONLY",
        "invocation_record_id": invocation.get("invocation_record_id"),
        "commit_invocation_ready": invocation.get("commit_invocation_ready") is True,
        "committed": False,
        "progress_updated": False,
        "cursor_advanced": False,
        "executor_imported": False,
        "scheduler_imported": False,
        "step_result_commit_called": False,
        "progress_mutated": False,
        "loop_continued": False,
        "automatic_retry_performed": False,
        "thread_created": False,
        "commit_invocation_envelope_only": True,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "RUNTIME_STEP_COMMIT_EXECUTION_ADAPTER_SCHEMA",
    "build_runtime_step_commit_invocation_record",
    "build_runtime_step_commit_execution_adapter_audit_projection",
    "build_runtime_step_commit_execution_adapter_audit_record",
    "build_runtime_step_commit_execution_adapter_milestone_seal",
]
