from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_EXECUTOR_INVOCATION_ADAPTER_SCHEMA = (
    "zero.runtime.executor_invocation_adapter.v1"
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


def _missing_authority(permit: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_AUTHORITY_FIELDS if not permit.get(field)]


def _envelope_id(
    *,
    runtime_id: str | None,
    permit_id: str | None,
    invocation_authorized: bool,
    blocked_reason: str,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "permit_id": permit_id,
            "invocation_authorized": invocation_authorized,
            "blocked_reason": blocked_reason,
        }
    )
    return f"runtime-executor-invocation-envelope::{runtime_id or 'missing-runtime'}::{fragment}"


def _executor_target(permit: dict[str, Any], authorized: bool) -> dict[str, Any]:
    if not authorized:
        return {}
    return {
        "runtime_id": permit.get("runtime_id"),
        "execution_lease_id": permit.get("execution_lease_id"),
        "capability_grant_id": permit.get("capability_grant_id"),
        "executor_binding_id": permit.get("executor_binding_id"),
        "target_mode": "invocation_envelope_only",
    }


def _payload_reference(permit: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_permit_id": permit.get("permit_id"),
        "source_execution_record_id": permit.get("source_execution_record_id"),
        "dispatch_reference": _as_mapping(permit.get("dispatch_reference")),
    }


def build_runtime_executor_invocation_envelope(
    runtime_invocation_permit: dict[str, Any] | None,
) -> dict[str, Any]:
    permit = _as_mapping(runtime_invocation_permit)
    missing = _missing_authority(permit)

    if permit.get("invocation_allowed") is not True:
        invocation_authorized = False
        blocked_reason = permit.get("denial_reason") or "permit_denied"
    elif permit.get("authority_verified") is not True:
        invocation_authorized = False
        blocked_reason = "authority_not_verified"
    elif missing:
        invocation_authorized = False
        blocked_reason = "missing_authority:" + ",".join(missing)
    else:
        invocation_authorized = True
        blocked_reason = "none"

    envelope_id = _envelope_id(
        runtime_id=permit.get("runtime_id"),
        permit_id=permit.get("permit_id"),
        invocation_authorized=invocation_authorized,
        blocked_reason=blocked_reason,
    )

    return {
        "schema": RUNTIME_EXECUTOR_INVOCATION_ADAPTER_SCHEMA,
        "envelope_id": envelope_id,
        "runtime_id": permit.get("runtime_id"),
        "source_permit_id": permit.get("permit_id"),
        "executor_target": _executor_target(permit, invocation_authorized),
        "invocation_authorized": invocation_authorized,
        "payload_reference": _payload_reference(permit),
        "execution_started": False,
        "executor_called": False,
        "result_expected": invocation_authorized,
        "blocked_reason": blocked_reason,
        "missing_authority": missing,
        "envelope_only": True,
        "executor_implementation_imported": False,
        "scheduler_imported": False,
        "command_executed": False,
        "files_mutated": False,
        "progress_mutated": False,
        "retry_scheduled": False,
        "loop_created": False,
        "thread_created": False,
    }


def build_runtime_executor_invocation_adapter_audit_projection(
    invocation_envelope: dict[str, Any] | None,
) -> dict[str, Any]:
    envelope = _as_mapping(invocation_envelope)
    return {
        "projection": "runtime_executor_invocation_adapter_audit",
        "projection_only": True,
        "envelope_id": envelope.get("envelope_id"),
        "runtime_id": envelope.get("runtime_id"),
        "source_permit_id": envelope.get("source_permit_id"),
        "invocation_authorized": envelope.get("invocation_authorized") is True,
        "payload_reference": _as_mapping(envelope.get("payload_reference")),
        "execution_started": False,
        "executor_called": False,
        "result_expected": envelope.get("result_expected") is True,
        "blocked_reason": envelope.get("blocked_reason", "not_evaluated"),
        "envelope_only": True,
        "executor_implementation_imported": False,
        "scheduler_imported": False,
        "command_executed": False,
        "files_mutated": False,
        "progress_mutated": False,
        "retry_scheduled": False,
        "loop_created": False,
        "thread_created": False,
    }


def build_runtime_executor_invocation_adapter_audit_record(
    runtime_invocation_permit: dict[str, Any] | None,
) -> dict[str, Any]:
    envelope = build_runtime_executor_invocation_envelope(runtime_invocation_permit)
    return {
        "audit_schema": RUNTIME_EXECUTOR_INVOCATION_ADAPTER_SCHEMA + ".audit",
        "decision": "reserved_runtime_executor_invocation_envelope_only",
        "runtime_executor_invocation_envelope": envelope,
        "audit_projection": build_runtime_executor_invocation_adapter_audit_projection(
            envelope
        ),
        "execution_started": False,
        "executor_called": False,
        "executor_implementation_imported": False,
        "scheduler_imported": False,
        "command_executed": False,
        "files_mutated": False,
        "progress_mutated": False,
        "retry_scheduled": False,
        "loop_created": False,
        "thread_created": False,
    }


def build_runtime_executor_invocation_adapter_milestone_seal(
    runtime_invocation_permit: dict[str, Any] | None,
) -> dict[str, Any]:
    audit = build_runtime_executor_invocation_adapter_audit_record(
        runtime_invocation_permit
    )
    envelope = _as_mapping(audit.get("runtime_executor_invocation_envelope"))
    return {
        "seal": "runtime_executor_invocation_adapter_bundle",
        "schema": RUNTIME_EXECUTOR_INVOCATION_ADAPTER_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_EXECUTOR_INVOCATION_ENVELOPES_ONLY",
        "envelope_id": envelope.get("envelope_id"),
        "invocation_authorized": envelope.get("invocation_authorized") is True,
        "result_expected": envelope.get("result_expected") is True,
        "execution_started": False,
        "executor_called": False,
        "executor_implementation_imported": False,
        "scheduler_imported": False,
        "command_executed": False,
        "files_mutated": False,
        "progress_mutated": False,
        "retry_scheduled": False,
        "loop_created": False,
        "thread_created": False,
        "envelope_only": True,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "RUNTIME_EXECUTOR_INVOCATION_ADAPTER_SCHEMA",
    "REQUIRED_AUTHORITY_FIELDS",
    "build_runtime_executor_invocation_envelope",
    "build_runtime_executor_invocation_adapter_audit_projection",
    "build_runtime_executor_invocation_adapter_audit_record",
    "build_runtime_executor_invocation_adapter_milestone_seal",
]
