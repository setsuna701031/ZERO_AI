from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_STEP_COMMIT_AUTHORITY_GATE_SCHEMA = (
    "zero.runtime.step_commit_authority_gate.v1"
)

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
    request: dict[str, Any],
    authority: dict[str, Any],
    field: str,
) -> Any:
    return authority.get(field) or request.get(field)


def _missing_authority(request: dict[str, Any], authority: dict[str, Any]) -> list[str]:
    return [
        field
        for field in REQUIRED_AUTHORITY_FIELDS
        if not _authority_value(request, authority, field)
    ]


def _authority_record_id(
    *,
    runtime_id: str | None,
    request_id: str | None,
    commit_authorized: bool,
    denial_reason: str,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "request_id": request_id,
            "commit_authorized": commit_authorized,
            "denial_reason": denial_reason,
        }
    )
    return f"runtime-step-commit-authority::{runtime_id or 'missing-runtime'}::{fragment}"


def build_runtime_step_commit_authority_record(
    runtime_step_result_commit_request: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = _as_mapping(runtime_step_result_commit_request)
    authority_record = _as_mapping(authority)
    missing = _missing_authority(request, authority_record)

    if request.get("commit_requested") is not True:
        commit_authorized = False
        denial_reason = request.get("blocked_reason") or "commit_not_requested"
    elif missing:
        commit_authorized = False
        denial_reason = "missing_authority:" + ",".join(missing)
    else:
        commit_authorized = True
        denial_reason = "none"

    authority_record_id = _authority_record_id(
        runtime_id=request.get("runtime_id"),
        request_id=request.get("step_result_commit_request_id"),
        commit_authorized=commit_authorized,
        denial_reason=denial_reason,
    )

    return {
        "schema": RUNTIME_STEP_COMMIT_AUTHORITY_GATE_SCHEMA,
        "authority_record_id": authority_record_id,
        "runtime_id": request.get("runtime_id"),
        "source_step_result_commit_request_id": request.get(
            "step_result_commit_request_id"
        ),
        "commit_authorized": commit_authorized,
        "result_kind": request.get("result_kind") or "noop",
        "result_summary": request.get("result_summary") or request.get("summary") or "",
        "summary": request.get("summary") or request.get("result_summary") or "",
        "failure_reason": request.get("failure_reason") or "none",
        "recovery_required": request.get("recovery_required") is True,
        "execution_lease_id": _authority_value(
            request, authority_record, "execution_lease_id"
        ),
        "capability_grant_id": _authority_value(
            request, authority_record, "capability_grant_id"
        ),
        "executor_binding_id": _authority_value(
            request, authority_record, "executor_binding_id"
        ),
        "missing_authority": missing,
        "denial_reason": denial_reason,
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
        "authority_record_only": True,
    }


def build_runtime_step_commit_authority_gate_audit_projection(
    authority_record: dict[str, Any] | None,
) -> dict[str, Any]:
    record = _as_mapping(authority_record)
    return {
        "projection": "runtime_step_commit_authority_gate_audit",
        "projection_only": True,
        "authority_record_id": record.get("authority_record_id"),
        "runtime_id": record.get("runtime_id"),
        "source_step_result_commit_request_id": record.get(
            "source_step_result_commit_request_id"
        ),
        "commit_authorized": record.get("commit_authorized") is True,
        "result_kind": record.get("result_kind"),
        "summary": record.get("summary"),
        "failure_reason": record.get("failure_reason", "none"),
        "recovery_required": record.get("recovery_required") is True,
        "denial_reason": record.get("denial_reason", "not_evaluated"),
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
        "authority_record_only": True,
    }


def build_runtime_step_commit_authority_gate_audit_record(
    runtime_step_result_commit_request: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = build_runtime_step_commit_authority_record(
        runtime_step_result_commit_request,
        authority=authority,
    )
    return {
        "audit_schema": RUNTIME_STEP_COMMIT_AUTHORITY_GATE_SCHEMA + ".audit",
        "decision": "reserved_runtime_step_commit_authority_record_only",
        "runtime_step_commit_authority_record": record,
        "audit_projection": build_runtime_step_commit_authority_gate_audit_projection(
            record
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


def build_runtime_step_commit_authority_gate_milestone_seal(
    runtime_step_result_commit_request: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = build_runtime_step_commit_authority_gate_audit_record(
        runtime_step_result_commit_request,
        authority=authority,
    )
    record = _as_mapping(audit.get("runtime_step_commit_authority_record"))
    return {
        "seal": "runtime_step_commit_authority_gate_bundle",
        "schema": RUNTIME_STEP_COMMIT_AUTHORITY_GATE_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_STEP_COMMIT_AUTHORITY_RECORDS_ONLY",
        "authority_record_id": record.get("authority_record_id"),
        "commit_authorized": record.get("commit_authorized") is True,
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
        "authority_record_only": True,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "RUNTIME_STEP_COMMIT_AUTHORITY_GATE_SCHEMA",
    "REQUIRED_AUTHORITY_FIELDS",
    "build_runtime_step_commit_authority_record",
    "build_runtime_step_commit_authority_gate_audit_projection",
    "build_runtime_step_commit_authority_gate_audit_record",
    "build_runtime_step_commit_authority_gate_milestone_seal",
]
