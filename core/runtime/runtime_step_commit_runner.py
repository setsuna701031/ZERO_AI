from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_STEP_COMMIT_RUNNER_SCHEMA = "zero.runtime.step_commit_runner.v1"

REQUIRED_AUTHORITY_FIELDS = (
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
    invocation: dict[str, Any],
    authority: dict[str, Any],
    field: str,
) -> Any:
    return authority.get(field) or invocation.get(field)


def _missing_authority(
    invocation: dict[str, Any],
    authority: dict[str, Any],
) -> list[str]:
    return [
        field
        for field in REQUIRED_AUTHORITY_FIELDS
        if not _authority_value(invocation, authority, field)
    ]


def _missing_metadata(invocation: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not invocation.get("result_kind"):
        missing.append("result_kind")
    if not (invocation.get("summary") or invocation.get("result_summary")):
        missing.append("summary")
    if "failure_reason" not in invocation:
        missing.append("failure_reason")
    if "recovery_required" not in invocation:
        missing.append("recovery_required")
    return missing


def _result_record_id(
    *,
    runtime_id: str | None,
    invocation_record_id: str | None,
    commit_completed: bool,
    denial_reason: str,
    result_kind: str | None,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "invocation_record_id": invocation_record_id,
            "commit_completed": commit_completed,
            "denial_reason": denial_reason,
            "result_kind": result_kind,
        }
    )
    return f"runtime-step-commit-result::{runtime_id or 'missing-runtime'}::{fragment}"


def _denial_reason(
    invocation: dict[str, Any],
    missing_authority: list[str],
    missing_metadata: list[str],
) -> str:
    reasons: list[str] = []
    if invocation.get("commit_invocation_ready") is not True:
        reasons.append(invocation.get("blocked_reason") or "commit_invocation_not_ready")
    if missing_authority:
        reasons.append("missing_authority:" + ",".join(missing_authority))
    if missing_metadata:
        reasons.append("missing_metadata:" + ",".join(missing_metadata))
    return ";".join(reasons) if reasons else "none"


def build_runtime_step_commit_result_record(
    runtime_step_commit_invocation_record: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    invocation = _as_mapping(runtime_step_commit_invocation_record)
    authority_record = _as_mapping(authority)
    missing_authority = _missing_authority(invocation, authority_record)
    missing_metadata = _missing_metadata(invocation)
    denial_reason = _denial_reason(
        invocation,
        missing_authority,
        missing_metadata,
    )
    commit_completed = denial_reason == "none"
    result_kind = invocation.get("result_kind") or "noop"
    summary = invocation.get("summary") or invocation.get("result_summary") or ""
    result_id = _result_record_id(
        runtime_id=invocation.get("runtime_id"),
        invocation_record_id=invocation.get("invocation_record_id"),
        commit_completed=commit_completed,
        denial_reason=denial_reason,
        result_kind=result_kind,
    )

    return {
        "schema": RUNTIME_STEP_COMMIT_RUNNER_SCHEMA,
        "step_commit_result_id": result_id,
        "runtime_id": invocation.get("runtime_id"),
        "source_invocation_record_id": invocation.get("invocation_record_id"),
        "source_authority_record_id": invocation.get("source_authority_record_id"),
        "source_step_result_commit_request_id": invocation.get(
            "source_step_result_commit_request_id"
        ),
        "commit_invocation_ready": invocation.get("commit_invocation_ready") is True,
        "commit_completed": commit_completed,
        "commit_denied": not commit_completed,
        "denial_reason": denial_reason,
        "result_kind": result_kind,
        "summary": summary,
        "result_summary": invocation.get("result_summary") or summary,
        "failure_reason": invocation.get("failure_reason") or "none",
        "recovery_required": invocation.get("recovery_required") is True,
        "execution_lease_id": _authority_value(
            invocation, authority_record, "execution_lease_id"
        ),
        "capability_grant_id": _authority_value(
            invocation, authority_record, "capability_grant_id"
        ),
        "executor_binding_id": _authority_value(
            invocation, authority_record, "executor_binding_id"
        ),
        "missing_authority": missing_authority,
        "missing_metadata": missing_metadata,
        "commit_result_record_only": True,
        "progress_updated": False,
        "cursor_advanced": False,
        "task_completion_mutated": False,
        "filesystem_mutation_performed": False,
        "direct_file_mutation_performed": False,
        "executor_imported": False,
        "scheduler_imported": False,
        "executor_called": False,
        "scheduler_called": False,
        "retry_loop_started": False,
        "daemon_started": False,
        "thread_created": False,
        "progress_mutated": False,
    }


def build_runtime_step_commit_runner_audit_projection(
    result_record: dict[str, Any] | None,
) -> dict[str, Any]:
    record = _as_mapping(result_record)
    return {
        "projection": "runtime_step_commit_runner_audit",
        "projection_only": True,
        "step_commit_result_id": record.get("step_commit_result_id"),
        "runtime_id": record.get("runtime_id"),
        "source_invocation_record_id": record.get("source_invocation_record_id"),
        "commit_completed": record.get("commit_completed") is True,
        "commit_denied": record.get("commit_denied") is True,
        "denial_reason": record.get("denial_reason", "not_evaluated"),
        "result_kind": record.get("result_kind"),
        "summary": record.get("summary"),
        "failure_reason": record.get("failure_reason", "none"),
        "recovery_required": record.get("recovery_required") is True,
        "progress_updated": False,
        "cursor_advanced": False,
        "task_completion_mutated": False,
        "filesystem_mutation_performed": False,
        "executor_imported": False,
        "scheduler_imported": False,
        "retry_loop_started": False,
        "daemon_started": False,
        "thread_created": False,
        "progress_mutated": False,
        "commit_result_record_only": True,
    }


def build_runtime_step_commit_runner_audit_record(
    runtime_step_commit_invocation_record: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = build_runtime_step_commit_result_record(
        runtime_step_commit_invocation_record,
        authority=authority,
    )
    return {
        "audit_schema": RUNTIME_STEP_COMMIT_RUNNER_SCHEMA + ".audit",
        "decision": "reserved_runtime_step_commit_result_record_only",
        "runtime_step_commit_result_record": result,
        "audit_projection": build_runtime_step_commit_runner_audit_projection(result),
        "commit_completed": result["commit_completed"],
        "commit_denied": result["commit_denied"],
        "progress_updated": False,
        "cursor_advanced": False,
        "task_completion_mutated": False,
        "filesystem_mutation_performed": False,
        "executor_imported": False,
        "scheduler_imported": False,
        "retry_loop_started": False,
        "daemon_started": False,
        "thread_created": False,
        "progress_mutated": False,
    }


def build_runtime_step_commit_runner_milestone_seal(
    runtime_step_commit_invocation_record: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = build_runtime_step_commit_runner_audit_record(
        runtime_step_commit_invocation_record,
        authority=authority,
    )
    result = _as_mapping(audit.get("runtime_step_commit_result_record"))
    return {
        "seal": "runtime_step_commit_runner_bundle",
        "schema": RUNTIME_STEP_COMMIT_RUNNER_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_STEP_COMMIT_RESULT_RECORDS_ONLY",
        "step_commit_result_id": result.get("step_commit_result_id"),
        "commit_completed": result.get("commit_completed") is True,
        "commit_denied": result.get("commit_denied") is True,
        "progress_updated": False,
        "cursor_advanced": False,
        "task_completion_mutated": False,
        "filesystem_mutation_performed": False,
        "executor_imported": False,
        "scheduler_imported": False,
        "retry_loop_started": False,
        "daemon_started": False,
        "thread_created": False,
        "progress_mutated": False,
        "commit_result_record_only": True,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "RUNTIME_STEP_COMMIT_RUNNER_SCHEMA",
    "REQUIRED_AUTHORITY_FIELDS",
    "build_runtime_step_commit_result_record",
    "build_runtime_step_commit_runner_audit_projection",
    "build_runtime_step_commit_runner_audit_record",
    "build_runtime_step_commit_runner_milestone_seal",
]
