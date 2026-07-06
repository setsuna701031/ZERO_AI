from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_STEP_RESULT_COMMIT_BRIDGE_SCHEMA = (
    "zero.runtime.step_result_commit_bridge.v1"
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _request_id(
    *,
    runtime_id: str | None,
    return_record_id: str | None,
    commit_requested: bool,
    result_kind: str | None,
    recovery_required: bool,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "return_record_id": return_record_id,
            "commit_requested": commit_requested,
            "result_kind": result_kind,
            "recovery_required": recovery_required,
        }
    )
    return f"runtime-step-result-commit-request::{runtime_id or 'missing-runtime'}::{fragment}"


def build_runtime_step_result_commit_request_bridge(
    runtime_execution_evidence_return_record: dict[str, Any] | None,
) -> dict[str, Any]:
    record = _as_mapping(runtime_execution_evidence_return_record)
    commit_ready = record.get("commit_ready") is True
    result_kind = record.get("result_kind") or "noop"
    summary = record.get("summary") or ""
    failure_reason = record.get("failure_reason") or "none"
    recovery_required = record.get("recovery_required") is True
    commit_requested = commit_ready
    blocked_reason = "none" if commit_requested else "evidence_not_commit_ready"
    request_id = _request_id(
        runtime_id=record.get("runtime_id"),
        return_record_id=record.get("return_record_id"),
        commit_requested=commit_requested,
        result_kind=result_kind,
        recovery_required=recovery_required,
    )

    return {
        "schema": RUNTIME_STEP_RESULT_COMMIT_BRIDGE_SCHEMA,
        "step_result_commit_request_id": request_id,
        "runtime_id": record.get("runtime_id"),
        "source_return_record_id": record.get("return_record_id"),
        "source_binding_record_id": record.get("source_binding_record_id"),
        "commit_requested": commit_requested,
        "result_kind": result_kind,
        "result_summary": summary,
        "summary": summary,
        "failure_reason": failure_reason,
        "recovery_required": recovery_required,
        "commit_input": _as_mapping(record.get("commit_input")),
        "blocked_reason": blocked_reason,
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
        "request_only": True,
    }


def build_runtime_step_result_commit_bridge_audit_projection(
    commit_request: dict[str, Any] | None,
) -> dict[str, Any]:
    request = _as_mapping(commit_request)
    return {
        "projection": "runtime_step_result_commit_bridge_audit",
        "projection_only": True,
        "step_result_commit_request_id": request.get("step_result_commit_request_id"),
        "runtime_id": request.get("runtime_id"),
        "source_return_record_id": request.get("source_return_record_id"),
        "commit_requested": request.get("commit_requested") is True,
        "result_kind": request.get("result_kind"),
        "summary": request.get("summary"),
        "failure_reason": request.get("failure_reason", "none"),
        "recovery_required": request.get("recovery_required") is True,
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
        "request_only": True,
    }


def build_runtime_step_result_commit_bridge_audit_record(
    runtime_execution_evidence_return_record: dict[str, Any] | None,
) -> dict[str, Any]:
    request = build_runtime_step_result_commit_request_bridge(
        runtime_execution_evidence_return_record
    )
    return {
        "audit_schema": RUNTIME_STEP_RESULT_COMMIT_BRIDGE_SCHEMA + ".audit",
        "decision": "reserved_runtime_step_result_commit_request_bridge_only",
        "runtime_step_result_commit_request": request,
        "audit_projection": build_runtime_step_result_commit_bridge_audit_projection(
            request
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


def build_runtime_step_result_commit_bridge_milestone_seal(
    runtime_execution_evidence_return_record: dict[str, Any] | None,
) -> dict[str, Any]:
    audit = build_runtime_step_result_commit_bridge_audit_record(
        runtime_execution_evidence_return_record
    )
    request = _as_mapping(audit.get("runtime_step_result_commit_request"))
    return {
        "seal": "runtime_step_result_commit_bridge_bundle",
        "schema": RUNTIME_STEP_RESULT_COMMIT_BRIDGE_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_STEP_RESULT_COMMIT_REQUESTS_ONLY",
        "step_result_commit_request_id": request.get("step_result_commit_request_id"),
        "commit_requested": request.get("commit_requested") is True,
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
        "request_only": True,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "RUNTIME_STEP_RESULT_COMMIT_BRIDGE_SCHEMA",
    "build_runtime_step_result_commit_request_bridge",
    "build_runtime_step_result_commit_bridge_audit_projection",
    "build_runtime_step_result_commit_bridge_audit_record",
    "build_runtime_step_result_commit_bridge_milestone_seal",
]
