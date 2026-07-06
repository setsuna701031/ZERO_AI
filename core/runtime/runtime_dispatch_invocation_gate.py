from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_DISPATCH_INVOCATION_GATE_SCHEMA = (
    "zero.runtime.dispatch_invocation_gate.v1"
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
    execution_record: dict[str, Any],
    authority: dict[str, Any],
    field: str,
) -> Any:
    return authority.get(field) or execution_record.get(field)


def _missing_authority(
    execution_record: dict[str, Any],
    authority: dict[str, Any],
) -> list[str]:
    return [
        field
        for field in REQUIRED_AUTHORITY_FIELDS
        if not _authority_value(execution_record, authority, field)
    ]


def _permit_id(
    *,
    runtime_id: str | None,
    source_execution_record_id: str | None,
    invocation_allowed: bool,
    denial_reason: str,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "source_execution_record_id": source_execution_record_id,
            "invocation_allowed": invocation_allowed,
            "denial_reason": denial_reason,
        }
    )
    return f"runtime-invocation-permit::{runtime_id or 'missing-runtime'}::{fragment}"


def _dispatch_reference(execution_record: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_loop_plan_id": execution_record.get("source_loop_plan_id"),
        "selected_tick_intent_id": execution_record.get("selected_tick_intent_id"),
        "execution_status": execution_record.get("execution_status"),
        "dispatch_allowed": execution_record.get("dispatch_allowed") is True,
    }


def build_runtime_invocation_permit(
    controlled_loop_plan_execution_record: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = _as_mapping(controlled_loop_plan_execution_record)
    authority_record = _as_mapping(authority)
    missing = _missing_authority(record, authority_record)

    if record.get("execution_status") != "ONE_TICK_SELECTED":
        invocation_allowed = False
        denial_reason = "execution_status_not_one_tick_selected"
    elif missing:
        invocation_allowed = False
        denial_reason = "missing_authority:" + ",".join(missing)
    else:
        invocation_allowed = True
        denial_reason = "none"

    authority_verified = invocation_allowed
    permit_id = _permit_id(
        runtime_id=record.get("runtime_id"),
        source_execution_record_id=record.get("execution_record_id"),
        invocation_allowed=invocation_allowed,
        denial_reason=denial_reason,
    )

    return {
        "schema": RUNTIME_DISPATCH_INVOCATION_GATE_SCHEMA,
        "permit_id": permit_id,
        "runtime_id": record.get("runtime_id"),
        "source_execution_record_id": record.get("execution_record_id"),
        "invocation_allowed": invocation_allowed,
        "executor_permission": "PERMIT_INVOCATION" if invocation_allowed else "DENY_INVOCATION",
        "dispatch_reference": _dispatch_reference(record),
        "denial_reason": denial_reason,
        "authority_verified": authority_verified,
        "execution_lease_id": _authority_value(record, authority_record, "execution_lease_id"),
        "capability_grant_id": _authority_value(record, authority_record, "capability_grant_id"),
        "executor_binding_id": _authority_value(record, authority_record, "executor_binding_id"),
        "missing_authority": missing,
        "executor_imported": False,
        "scheduler_imported": False,
        "step_executed": False,
        "progress_mutated": False,
        "loop_continued": False,
        "automatic_retry_performed": False,
        "thread_created": False,
        "executor_called": False,
        "scheduler_called": False,
        "permit_only": True,
    }


def build_runtime_dispatch_invocation_gate_audit_projection(
    invocation_permit: dict[str, Any] | None,
) -> dict[str, Any]:
    permit = _as_mapping(invocation_permit)
    return {
        "projection": "runtime_dispatch_invocation_gate_audit",
        "projection_only": True,
        "permit_id": permit.get("permit_id"),
        "runtime_id": permit.get("runtime_id"),
        "source_execution_record_id": permit.get("source_execution_record_id"),
        "invocation_allowed": permit.get("invocation_allowed") is True,
        "executor_permission": permit.get("executor_permission", "DENY_INVOCATION"),
        "dispatch_reference": _as_mapping(permit.get("dispatch_reference")),
        "denial_reason": permit.get("denial_reason", "not_evaluated"),
        "authority_verified": permit.get("authority_verified") is True,
        "executor_imported": False,
        "scheduler_imported": False,
        "step_executed": False,
        "progress_mutated": False,
        "loop_continued": False,
        "automatic_retry_performed": False,
        "thread_created": False,
        "executor_called": False,
        "scheduler_called": False,
        "permit_only": True,
    }


def build_runtime_dispatch_invocation_gate_audit_record(
    controlled_loop_plan_execution_record: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    permit = build_runtime_invocation_permit(
        controlled_loop_plan_execution_record,
        authority=authority,
    )
    return {
        "audit_schema": RUNTIME_DISPATCH_INVOCATION_GATE_SCHEMA + ".audit",
        "decision": "reserved_runtime_dispatch_invocation_permit_only",
        "runtime_invocation_permit": permit,
        "audit_projection": build_runtime_dispatch_invocation_gate_audit_projection(
            permit
        ),
        "executor_imported": False,
        "scheduler_imported": False,
        "step_executed": False,
        "progress_mutated": False,
        "loop_continued": False,
        "automatic_retry_performed": False,
        "thread_created": False,
        "executor_called": False,
        "scheduler_called": False,
    }


def build_runtime_dispatch_invocation_gate_milestone_seal(
    controlled_loop_plan_execution_record: dict[str, Any] | None,
    *,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = build_runtime_dispatch_invocation_gate_audit_record(
        controlled_loop_plan_execution_record,
        authority=authority,
    )
    permit = _as_mapping(audit.get("runtime_invocation_permit"))
    return {
        "seal": "runtime_dispatch_invocation_gate_bundle",
        "schema": RUNTIME_DISPATCH_INVOCATION_GATE_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_INVOCATION_PERMITS_ONLY",
        "permit_id": permit.get("permit_id"),
        "invocation_allowed": permit.get("invocation_allowed") is True,
        "authority_verified": permit.get("authority_verified") is True,
        "executor_imported": False,
        "scheduler_imported": False,
        "step_executed": False,
        "progress_mutated": False,
        "loop_continued": False,
        "automatic_retry_performed": False,
        "thread_created": False,
        "executor_called": False,
        "scheduler_called": False,
        "permit_only": True,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "RUNTIME_DISPATCH_INVOCATION_GATE_SCHEMA",
    "REQUIRED_AUTHORITY_FIELDS",
    "build_runtime_invocation_permit",
    "build_runtime_dispatch_invocation_gate_audit_projection",
    "build_runtime_dispatch_invocation_gate_audit_record",
    "build_runtime_dispatch_invocation_gate_milestone_seal",
]
