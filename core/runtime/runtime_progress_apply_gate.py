from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_PROGRESS_APPLY_GATE_SCHEMA = "zero.runtime.progress_apply_gate.v1"

REQUIRED_COMMIT_AUTHORITY_FIELDS = (
    "execution_lease_id",
    "capability_grant_id",
    "executor_binding_id",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _authority_value(
    commit_result: dict[str, Any],
    authority: dict[str, Any],
    field: str,
) -> Any:
    return authority.get(field) or commit_result.get(field)


def _missing_authority(
    commit_result: dict[str, Any],
    authority: dict[str, Any],
) -> list[str]:
    return [
        field
        for field in REQUIRED_COMMIT_AUTHORITY_FIELDS
        if not _authority_value(commit_result, authority, field)
    ]


def _missing_metadata(commit_result: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not commit_result.get("result_kind"):
        missing.append("result_kind")
    if not (commit_result.get("summary") or commit_result.get("result_summary")):
        missing.append("summary")
    if "failure_reason" not in commit_result:
        missing.append("failure_reason")
    if "recovery_required" not in commit_result:
        missing.append("recovery_required")
    return missing


def _denial_reason(
    commit_result: dict[str, Any],
    missing_authority: list[str],
    missing_metadata: list[str],
) -> str:
    reasons: list[str] = []
    if commit_result.get("commit_completed") is not True:
        reasons.append(commit_result.get("denial_reason") or "commit_not_completed")
    if missing_authority:
        reasons.append("missing_authority:" + ",".join(missing_authority))
    if missing_metadata:
        reasons.append("missing_metadata:" + ",".join(missing_metadata))
    return ";".join(reasons) if reasons else "none"


def _progress_apply_record_id(
    *,
    runtime_id: str | None,
    step_commit_result_id: str | None,
    progress_apply_allowed: bool,
    denial_reason: str,
    result_kind: str | None,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "step_commit_result_id": step_commit_result_id,
            "progress_apply_allowed": progress_apply_allowed,
            "denial_reason": denial_reason,
            "result_kind": result_kind,
        }
    )
    return f"runtime-progress-apply::{runtime_id or 'missing-runtime'}::{fragment}"


def build_runtime_progress_apply_record(
    runtime_step_commit_result_record: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    commit_result = _as_mapping(runtime_step_commit_result_record)
    authority_record = _as_mapping(authority)
    missing_authority = _missing_authority(commit_result, authority_record)
    missing_metadata = _missing_metadata(commit_result)
    denial_reason = _denial_reason(
        commit_result,
        missing_authority,
        missing_metadata,
    )
    progress_apply_allowed = denial_reason == "none"
    result_kind = commit_result.get("result_kind") or "noop"
    summary = commit_result.get("summary") or commit_result.get("result_summary") or ""
    progress_apply_id = _progress_apply_record_id(
        runtime_id=commit_result.get("runtime_id"),
        step_commit_result_id=commit_result.get("step_commit_result_id"),
        progress_apply_allowed=progress_apply_allowed,
        denial_reason=denial_reason,
        result_kind=result_kind,
    )

    return {
        "schema": RUNTIME_PROGRESS_APPLY_GATE_SCHEMA,
        "progress_apply_record_id": progress_apply_id,
        "runtime_id": commit_result.get("runtime_id"),
        "source_step_commit_result_id": commit_result.get("step_commit_result_id"),
        "source_invocation_record_id": commit_result.get(
            "source_invocation_record_id"
        ),
        "source_authority_record_id": commit_result.get("source_authority_record_id"),
        "source_step_result_commit_request_id": commit_result.get(
            "source_step_result_commit_request_id"
        ),
        "commit_completed": commit_result.get("commit_completed") is True,
        "progress_apply_allowed": progress_apply_allowed,
        "progress_record_created": progress_apply_allowed,
        "progress_apply_denied": not progress_apply_allowed,
        "denial_reason": denial_reason,
        "result_kind": result_kind,
        "summary": summary,
        "result_summary": commit_result.get("result_summary") or summary,
        "failure_reason": commit_result.get("failure_reason") or "none",
        "recovery_required": commit_result.get("recovery_required") is True,
        "execution_lease_id": _authority_value(
            commit_result, authority_record, "execution_lease_id"
        ),
        "capability_grant_id": _authority_value(
            commit_result, authority_record, "capability_grant_id"
        ),
        "executor_binding_id": _authority_value(
            commit_result, authority_record, "executor_binding_id"
        ),
        "missing_authority": missing_authority,
        "missing_metadata": missing_metadata,
        "progress_apply_record_only": True,
        "cursor_advanced": False,
        "next_tick_requested": False,
        "executor_imported": False,
        "scheduler_imported": False,
        "loop_continued": False,
        "automatic_retry_performed": False,
        "retry_scheduled": False,
        "daemon_started": False,
        "thread_created": False,
    }


def build_runtime_progress_apply_gate_audit_projection(
    progress_apply_record: dict[str, Any] | None,
) -> dict[str, Any]:
    record = _as_mapping(progress_apply_record)
    return {
        "projection": "runtime_progress_apply_gate_audit",
        "projection_only": True,
        "progress_apply_record_id": record.get("progress_apply_record_id"),
        "runtime_id": record.get("runtime_id"),
        "source_step_commit_result_id": record.get("source_step_commit_result_id"),
        "progress_apply_allowed": record.get("progress_apply_allowed") is True,
        "progress_record_created": record.get("progress_record_created") is True,
        "progress_apply_denied": record.get("progress_apply_denied") is True,
        "denial_reason": record.get("denial_reason", "not_evaluated"),
        "result_kind": record.get("result_kind"),
        "summary": record.get("summary"),
        "failure_reason": record.get("failure_reason", "none"),
        "recovery_required": record.get("recovery_required") is True,
        "cursor_advanced": False,
        "next_tick_requested": False,
        "executor_imported": False,
        "scheduler_imported": False,
        "loop_continued": False,
        "automatic_retry_performed": False,
        "daemon_started": False,
        "thread_created": False,
        "progress_apply_record_only": True,
    }


def build_runtime_progress_apply_gate_audit_record(
    runtime_step_commit_result_record: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = build_runtime_progress_apply_record(
        runtime_step_commit_result_record,
        authority=authority,
    )
    return {
        "audit_schema": RUNTIME_PROGRESS_APPLY_GATE_SCHEMA + ".audit",
        "decision": "reserved_runtime_progress_apply_record_only",
        "runtime_progress_apply_record": record,
        "audit_projection": build_runtime_progress_apply_gate_audit_projection(record),
        "progress_apply_allowed": record["progress_apply_allowed"],
        "progress_record_created": record["progress_record_created"],
        "cursor_advanced": False,
        "next_tick_requested": False,
        "executor_imported": False,
        "scheduler_imported": False,
        "loop_continued": False,
        "automatic_retry_performed": False,
        "daemon_started": False,
        "thread_created": False,
    }


def build_runtime_progress_apply_gate_milestone_seal(
    runtime_step_commit_result_record: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = build_runtime_progress_apply_gate_audit_record(
        runtime_step_commit_result_record,
        authority=authority,
    )
    record = _as_mapping(audit.get("runtime_progress_apply_record"))
    return {
        "seal": "runtime_progress_apply_gate_bundle",
        "schema": RUNTIME_PROGRESS_APPLY_GATE_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_PROGRESS_APPLY_RECORDS_ONLY",
        "progress_apply_record_id": record.get("progress_apply_record_id"),
        "progress_apply_allowed": record.get("progress_apply_allowed") is True,
        "progress_record_created": record.get("progress_record_created") is True,
        "cursor_advanced": False,
        "next_tick_requested": False,
        "executor_imported": False,
        "scheduler_imported": False,
        "loop_continued": False,
        "automatic_retry_performed": False,
        "daemon_started": False,
        "thread_created": False,
        "progress_apply_record_only": True,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "RUNTIME_PROGRESS_APPLY_GATE_SCHEMA",
    "REQUIRED_COMMIT_AUTHORITY_FIELDS",
    "build_runtime_progress_apply_record",
    "build_runtime_progress_apply_gate_audit_projection",
    "build_runtime_progress_apply_gate_audit_record",
    "build_runtime_progress_apply_gate_milestone_seal",
]
