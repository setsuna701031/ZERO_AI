from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_EXECUTOR_BINDING_GATE_SCHEMA = "zero.runtime.executor_binding_gate.v1"

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
    envelope: dict[str, Any],
    authority: dict[str, Any],
    field: str,
) -> Any:
    target = _as_mapping(envelope.get("executor_target"))
    return authority.get(field) or envelope.get(field) or target.get(field)


def _missing_authority(envelope: dict[str, Any], authority: dict[str, Any]) -> list[str]:
    return [
        field
        for field in REQUIRED_AUTHORITY_FIELDS
        if not _authority_value(envelope, authority, field)
    ]


def _binding_record_id(
    *,
    runtime_id: str | None,
    envelope_id: str | None,
    execution_bound: bool,
    blocked_reason: str,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "envelope_id": envelope_id,
            "execution_bound": execution_bound,
            "blocked_reason": blocked_reason,
        }
    )
    return f"runtime-executor-binding-record::{runtime_id or 'missing-runtime'}::{fragment}"


def build_runtime_executor_binding_record(
    runtime_executor_invocation_envelope: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    envelope = _as_mapping(runtime_executor_invocation_envelope)
    authority_record = _as_mapping(authority)
    missing = _missing_authority(envelope, authority_record)

    if envelope.get("invocation_authorized") is not True:
        execution_bound = False
        blocked_reason = envelope.get("blocked_reason") or "invocation_not_authorized"
    elif missing:
        execution_bound = False
        blocked_reason = "missing_authority:" + ",".join(missing)
    else:
        execution_bound = True
        blocked_reason = "none"

    binding_record_id = _binding_record_id(
        runtime_id=envelope.get("runtime_id"),
        envelope_id=envelope.get("envelope_id"),
        execution_bound=execution_bound,
        blocked_reason=blocked_reason,
    )

    return {
        "schema": RUNTIME_EXECUTOR_BINDING_GATE_SCHEMA,
        "binding_record_id": binding_record_id,
        "runtime_id": envelope.get("runtime_id"),
        "source_envelope_id": envelope.get("envelope_id"),
        "source_permit_id": envelope.get("source_permit_id"),
        "execution_bound": execution_bound,
        "binding_status": "bound" if execution_bound else "blocked",
        "execution_lease_id": _authority_value(envelope, authority_record, "execution_lease_id"),
        "capability_grant_id": _authority_value(envelope, authority_record, "capability_grant_id"),
        "executor_binding_id": _authority_value(envelope, authority_record, "executor_binding_id"),
        "payload_reference": _as_mapping(envelope.get("payload_reference")),
        "result_commit_required": execution_bound,
        "execution_started": False,
        "executor_called": False,
        "command_executed": False,
        "scheduler_imported": False,
        "progress_mutated": False,
        "loop_created": False,
        "thread_created": False,
        "retry_scheduled": False,
        "executor_implementation_imported": False,
        "blocked_reason": blocked_reason,
        "missing_authority": missing,
        "binding_record_only": True,
    }


def build_runtime_executor_binding_gate_audit_projection(
    binding_record: dict[str, Any] | None,
) -> dict[str, Any]:
    record = _as_mapping(binding_record)
    return {
        "projection": "runtime_executor_binding_gate_audit",
        "projection_only": True,
        "binding_record_id": record.get("binding_record_id"),
        "runtime_id": record.get("runtime_id"),
        "source_envelope_id": record.get("source_envelope_id"),
        "source_permit_id": record.get("source_permit_id"),
        "execution_bound": record.get("execution_bound") is True,
        "binding_status": record.get("binding_status", "blocked"),
        "result_commit_required": record.get("result_commit_required") is True,
        "execution_started": False,
        "executor_called": False,
        "command_executed": False,
        "scheduler_imported": False,
        "progress_mutated": False,
        "loop_created": False,
        "thread_created": False,
        "retry_scheduled": False,
        "executor_implementation_imported": False,
        "blocked_reason": record.get("blocked_reason", "not_evaluated"),
        "binding_record_only": True,
    }


def build_runtime_executor_binding_gate_audit_record(
    runtime_executor_invocation_envelope: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = build_runtime_executor_binding_record(
        runtime_executor_invocation_envelope,
        authority=authority,
    )
    return {
        "audit_schema": RUNTIME_EXECUTOR_BINDING_GATE_SCHEMA + ".audit",
        "decision": "reserved_runtime_executor_binding_record_only",
        "runtime_executor_binding_record": record,
        "audit_projection": build_runtime_executor_binding_gate_audit_projection(
            record
        ),
        "execution_started": False,
        "executor_called": False,
        "command_executed": False,
        "scheduler_imported": False,
        "progress_mutated": False,
        "loop_created": False,
        "thread_created": False,
        "retry_scheduled": False,
        "executor_implementation_imported": False,
    }


def build_runtime_executor_binding_gate_milestone_seal(
    runtime_executor_invocation_envelope: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = build_runtime_executor_binding_gate_audit_record(
        runtime_executor_invocation_envelope,
        authority=authority,
    )
    record = _as_mapping(audit.get("runtime_executor_binding_record"))
    return {
        "seal": "runtime_executor_binding_gate_bundle",
        "schema": RUNTIME_EXECUTOR_BINDING_GATE_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_EXECUTOR_BINDING_RECORDS_ONLY",
        "binding_record_id": record.get("binding_record_id"),
        "execution_bound": record.get("execution_bound") is True,
        "result_commit_required": record.get("result_commit_required") is True,
        "execution_started": False,
        "executor_called": False,
        "command_executed": False,
        "scheduler_imported": False,
        "progress_mutated": False,
        "loop_created": False,
        "thread_created": False,
        "retry_scheduled": False,
        "executor_implementation_imported": False,
        "binding_record_only": True,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "RUNTIME_EXECUTOR_BINDING_GATE_SCHEMA",
    "REQUIRED_AUTHORITY_FIELDS",
    "build_runtime_executor_binding_record",
    "build_runtime_executor_binding_gate_audit_projection",
    "build_runtime_executor_binding_gate_audit_record",
    "build_runtime_executor_binding_gate_milestone_seal",
]
