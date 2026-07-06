from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_EXECUTION_EVIDENCE_RETURN_PATH_SCHEMA = (
    "zero.runtime.execution_evidence_return_path.v1"
)

SUPPORTED_RESULT_KINDS = (
    "noop",
    "read_result",
    "write_result",
    "mutation_result",
    "recovery_result",
    "failure_result",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _return_record_id(
    *,
    runtime_id: str | None,
    binding_record_id: str | None,
    evidence_accepted: bool,
    result_kind: str,
    failure_reason: str,
    recovery_required: bool,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "binding_record_id": binding_record_id,
            "evidence_accepted": evidence_accepted,
            "result_kind": result_kind,
            "failure_reason": failure_reason,
            "recovery_required": recovery_required,
        }
    )
    return f"runtime-execution-evidence-return::{runtime_id or 'missing-runtime'}::{fragment}"


def _normalize_result_kind(evidence: dict[str, Any]) -> str:
    result_kind = evidence.get("result_kind") or evidence.get("kind") or "noop"
    return str(result_kind) if result_kind in SUPPORTED_RESULT_KINDS else "noop"


def build_runtime_execution_evidence_return_record(
    runtime_executor_binding_record: dict[str, Any] | None,
    executor_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    binding = _as_mapping(runtime_executor_binding_record)
    evidence = _as_mapping(executor_evidence)
    result_kind = _normalize_result_kind(evidence)
    summary = str(evidence.get("summary") or evidence.get("result_summary") or "")
    failure_reason = str(evidence.get("failure_reason") or "none")
    recovery_required = (
        evidence.get("recovery_required") is True or result_kind == "recovery_result"
    )

    if binding.get("execution_bound") is not True:
        evidence_accepted = False
        blocked_reason = "execution_not_bound"
    elif binding.get("result_commit_required") is not True:
        evidence_accepted = False
        blocked_reason = "result_commit_not_required"
    elif evidence.get("caller_supplied") is not True:
        evidence_accepted = False
        blocked_reason = "missing_caller_supplied_evidence"
    else:
        evidence_accepted = True
        blocked_reason = "none"
        if not summary:
            summary = "caller_supplied_executor_evidence"

    commit_ready = evidence_accepted
    return_record_id = _return_record_id(
        runtime_id=binding.get("runtime_id"),
        binding_record_id=binding.get("binding_record_id"),
        evidence_accepted=evidence_accepted,
        result_kind=result_kind,
        failure_reason=failure_reason,
        recovery_required=recovery_required,
    )

    return {
        "schema": RUNTIME_EXECUTION_EVIDENCE_RETURN_PATH_SCHEMA,
        "return_record_id": return_record_id,
        "runtime_id": binding.get("runtime_id"),
        "source_binding_record_id": binding.get("binding_record_id"),
        "evidence_accepted": evidence_accepted,
        "result_kind": result_kind,
        "summary": summary,
        "failure_reason": failure_reason,
        "recovery_required": recovery_required,
        "commit_ready": commit_ready,
        "executor_called": False,
        "execution_inferred": False,
        "blocked_reason": blocked_reason,
        "caller_supplied": evidence.get("caller_supplied") is True,
        "commit_input": {
            "result_kind": result_kind,
            "result_summary": summary,
            "failure_reason": failure_reason,
            "recovery_required": recovery_required,
            "source_binding_record_id": binding.get("binding_record_id"),
        }
        if commit_ready
        else {},
        "scheduler_imported": False,
        "progress_mutated": False,
        "retry_scheduled": False,
        "loop_created": False,
        "thread_created": False,
    }


def build_runtime_execution_evidence_return_path_audit_projection(
    return_record: dict[str, Any] | None,
) -> dict[str, Any]:
    record = _as_mapping(return_record)
    return {
        "projection": "runtime_execution_evidence_return_path_audit",
        "projection_only": True,
        "return_record_id": record.get("return_record_id"),
        "runtime_id": record.get("runtime_id"),
        "source_binding_record_id": record.get("source_binding_record_id"),
        "evidence_accepted": record.get("evidence_accepted") is True,
        "result_kind": record.get("result_kind"),
        "summary": record.get("summary"),
        "failure_reason": record.get("failure_reason", "none"),
        "recovery_required": record.get("recovery_required") is True,
        "commit_ready": record.get("commit_ready") is True,
        "executor_called": False,
        "execution_inferred": False,
        "scheduler_imported": False,
        "progress_mutated": False,
        "retry_scheduled": False,
        "loop_created": False,
        "thread_created": False,
    }


def build_runtime_execution_evidence_return_path_audit_record(
    runtime_executor_binding_record: dict[str, Any] | None,
    executor_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = build_runtime_execution_evidence_return_record(
        runtime_executor_binding_record,
        executor_evidence,
    )
    return {
        "audit_schema": RUNTIME_EXECUTION_EVIDENCE_RETURN_PATH_SCHEMA + ".audit",
        "decision": "reserved_runtime_execution_evidence_return_path_record_only",
        "runtime_execution_evidence_return_record": record,
        "audit_projection": build_runtime_execution_evidence_return_path_audit_projection(
            record
        ),
        "executor_called": False,
        "execution_inferred": False,
        "scheduler_imported": False,
        "progress_mutated": False,
        "retry_scheduled": False,
        "loop_created": False,
        "thread_created": False,
    }


def build_runtime_execution_evidence_return_path_milestone_seal(
    runtime_executor_binding_record: dict[str, Any] | None,
    executor_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = build_runtime_execution_evidence_return_path_audit_record(
        runtime_executor_binding_record,
        executor_evidence,
    )
    record = _as_mapping(audit.get("runtime_execution_evidence_return_record"))
    return {
        "seal": "runtime_execution_evidence_return_path_bundle",
        "schema": RUNTIME_EXECUTION_EVIDENCE_RETURN_PATH_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_EXECUTION_EVIDENCE_RETURN_RECORDS_ONLY",
        "return_record_id": record.get("return_record_id"),
        "evidence_accepted": record.get("evidence_accepted") is True,
        "commit_ready": record.get("commit_ready") is True,
        "executor_called": False,
        "execution_inferred": False,
        "scheduler_imported": False,
        "progress_mutated": False,
        "retry_scheduled": False,
        "loop_created": False,
        "thread_created": False,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "RUNTIME_EXECUTION_EVIDENCE_RETURN_PATH_SCHEMA",
    "SUPPORTED_RESULT_KINDS",
    "build_runtime_execution_evidence_return_record",
    "build_runtime_execution_evidence_return_path_audit_projection",
    "build_runtime_execution_evidence_return_path_audit_record",
    "build_runtime_execution_evidence_return_path_milestone_seal",
]
