from __future__ import annotations

from copy import deepcopy
from typing import Any


RUNTIME_EXECUTOR_BINDING_SCHEMA = "zero.runtime.executor_binding.v1"

AUTHORIZED_EXECUTOR_BIND_DECISION = "AUTHORIZE_EXECUTOR_BINDING_RECORD_ONLY"

EXECUTOR_BINDING_STATES = ("detached", "bound", "revoked", "expired")

EXECUTOR_TYPES = (
    "task_executor",
    "tool_executor",
    "mutation_executor",
    "recovery_executor",
)

REQUIRED_EXECUTOR_BINDING_FIELDS = (
    "binding_request_id",
    "runtime_session_id",
    "execution_lease",
    "capability_grant",
    "executor_id",
    "executor_type",
    "authorization_input",
    "expiration_model",
    "revocation_model",
    "audit_required",
)

EXECUTOR_BINDING_BOUNDARY_LOCKS = {
    "executor_enabled": False,
    "executor_start_allowed": False,
    "task_execution_allowed": False,
    "subprocess_allowed": False,
    "file_mutation_allowed": False,
    "io_allowed": False,
    "tool_call_allowed": False,
    "autonomy_allowed": False,
    "self_start_allowed": False,
    "background_loop_allowed": False,
    "execution_allowed": False,
    "mutation_allowed": False,
}

REQUIRED_BLOCKERS = (
    "runtime_session_id_required",
    "active_execution_lease_required",
    "active_capability_grant_required",
    "explicit_bind_authorization_required",
    "executor_binding_record_only",
    "all_executors_default_disabled",
    "executor_start_locked",
    "task_execution_locked",
    "subprocess_locked",
    "file_mutation_locked",
    "io_locked",
    "tool_call_locked",
    "autonomy_locked",
    "self_start_locked",
    "background_loop_locked",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_EXECUTOR_BINDING_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in EXECUTOR_BINDING_BOUNDARY_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _binding_id(
    binding_request_id: str,
    session_id: str,
    lease_id: str,
    capability_grant_id: str,
    executor_id: str,
) -> str:
    return (
        f"executor-binding::{session_id}::{lease_id}::"
        f"{capability_grant_id}::{executor_id}::{binding_request_id}"
    )


def build_runtime_executor_binding_request(
    *,
    binding_request_id: str,
    runtime_session_id: str | None = None,
    execution_lease: dict[str, Any] | None = None,
    capability_grant: dict[str, Any] | None = None,
    executor_id: str | None = None,
    executor_type: str = "task_executor",
    authorization_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_EXECUTOR_BINDING_SCHEMA,
        "binding_request_id": binding_request_id,
        "runtime_session_id": runtime_session_id,
        "execution_lease": (
            deepcopy(execution_lease) if execution_lease is not None else {}
        ),
        "capability_grant": (
            deepcopy(capability_grant) if capability_grant is not None else {}
        ),
        "executor_id": executor_id,
        "executor_type": executor_type,
        "authorization_input": (
            deepcopy(authorization_input)
            if authorization_input is not None
            else {
                "decision": "NO_GO",
                "explicit_bind_authorization": False,
                "authorize_executor_binding_record": False,
            }
        ),
        "expiration_model": {
            "model": "deterministic_counter",
            "expires_at_tick": 1,
            "current_tick": 0,
            "expired": False,
        },
        "revocation_model": {
            "revocable": True,
            "revoked": False,
            "revocation_reason": None,
        },
        "boundary_locks": deepcopy(EXECUTOR_BINDING_BOUNDARY_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def validate_runtime_executor_binding_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    session_id = record.get("runtime_session_id")
    lease = _as_mapping(record.get("execution_lease"))
    grant = _as_mapping(record.get("capability_grant"))
    authorization = _as_mapping(record.get("authorization_input"))
    executor_id = record.get("executor_id")
    executor_type = record.get("executor_type")

    lease_id = lease.get("lease_id")
    capability_grant_id = grant.get("capability_grant_id")
    active_lease = (
        bool(lease_id)
        and lease.get("runtime_session_id") == session_id
        and lease.get("lease_status") == "granted"
    )
    active_grant = (
        bool(capability_grant_id)
        and grant.get("owner_session_id") == session_id
        and grant.get("owner_lease_id") == lease_id
        and grant.get("grant_status") == "granted"
    )
    authorized = (
        authorization.get("decision") == AUTHORIZED_EXECUTOR_BIND_DECISION
        and authorization.get("explicit_bind_authorization") is True
        and authorization.get("authorize_executor_binding_record") is True
    )

    problems: list[str] = []
    if missing:
        problems.append("missing_required_fields")
    if missing_blockers:
        problems.append("missing_required_blockers")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if not session_id:
        problems.append("invalid_runtime_session_id")
    if not active_lease:
        problems.append("inactive_execution_lease")
    if not active_grant:
        problems.append("inactive_capability_grant")
    if not executor_id:
        problems.append("invalid_executor_id")
    if executor_type not in EXECUTOR_TYPES:
        problems.append("invalid_executor_type")
    if not authorized:
        problems.append("executor_bind_authorization_missing")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")

    binding_record = (
        build_runtime_executor_binding_record(record)
        if not problems
        else None
    )

    return {
        "schema": RUNTIME_EXECUTOR_BINDING_SCHEMA,
        "valid": not problems,
        "binding_request_id": record.get("binding_request_id"),
        "runtime_session_id": session_id,
        "execution_lease_id": lease_id,
        "capability_grant_id": capability_grant_id,
        "status": "accepted_executor_binding_record_request"
        if not problems
        else "blocked",
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "binding_created": binding_record is not None,
        "executor_binding_record": binding_record,
        "executor_enabled": False,
        "executor_started": False,
        "executor_start_allowed": False,
        "task_execution_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "file_mutation_allowed": False,
        "io_allowed": False,
        "tool_call_allowed": False,
        "autonomy_allowed": False,
        "self_start_allowed": False,
        "background_loop_allowed": False,
        "audit_required": True,
    }


def build_runtime_executor_binding_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    lease = _as_mapping(record.get("execution_lease"))
    grant = _as_mapping(record.get("capability_grant"))
    session_id = str(record.get("runtime_session_id"))
    lease_id = str(lease.get("lease_id"))
    capability_grant_id = str(grant.get("capability_grant_id"))
    executor_id = str(record.get("executor_id"))
    request_id = str(record.get("binding_request_id"))

    return {
        "executor_binding_id": _binding_id(
            request_id,
            session_id,
            lease_id,
            capability_grant_id,
            executor_id,
        ),
        "runtime_session_id": session_id,
        "execution_lease_id": lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_id": executor_id,
        "executor_type": record.get("executor_type"),
        "binding_status": "bound",
        "supported_states": list(EXECUTOR_BINDING_STATES),
        "reserved_executor_types": list(EXECUTOR_TYPES),
        "expiration_model": _as_mapping(record.get("expiration_model")),
        "revocation_model": _as_mapping(record.get("revocation_model")),
        "record_only": True,
        "executor_enabled": False,
        "executor_started": False,
        "executor_start_allowed": False,
        "task_execution_allowed": False,
        "subprocess_allowed": False,
        "file_mutation_allowed": False,
        "io_allowed": False,
        "tool_call_allowed": False,
        "autonomy_allowed": False,
        "self_start_allowed": False,
        "background_loop_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
    }


def expire_runtime_executor_binding(
    binding_record: dict[str, Any],
    *,
    current_tick: int,
) -> dict[str, Any]:
    binding = _as_mapping(binding_record)
    expiration = _as_mapping(binding.get("expiration_model"))
    expires_at = expiration.get("expires_at_tick", 0)
    expired = current_tick >= expires_at
    expiration["current_tick"] = current_tick
    expiration["expired"] = expired
    if expired:
        binding["binding_status"] = "expired"
    binding["expiration_model"] = expiration
    binding["executor_enabled"] = False
    binding["executor_start_allowed"] = False
    binding["execution_allowed"] = False
    return binding


def revoke_runtime_executor_binding(
    binding_record: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    binding = _as_mapping(binding_record)
    revocation = _as_mapping(binding.get("revocation_model"))
    revocation["revoked"] = True
    revocation["revocation_reason"] = reason
    binding["revocation_model"] = revocation
    binding["binding_status"] = "revoked"
    binding["executor_enabled"] = False
    binding["executor_start_allowed"] = False
    binding["execution_allowed"] = False
    return binding


def can_runtime_executor_binding_authorize_execution(
    binding_record: dict[str, Any],
) -> dict[str, Any]:
    binding = _as_mapping(binding_record)
    status = binding.get("binding_status", "detached")
    if status == "expired":
        reason = "executor_binding_expired"
    elif status == "revoked":
        reason = "executor_binding_revoked"
    elif status != "bound":
        reason = "executor_binding_not_bound"
    else:
        reason = "executor_disabled"

    return {
        "executor_binding_id": binding.get("executor_binding_id"),
        "binding_status": status,
        "executor_enabled": False,
        "can_authorize_execution": False,
        "blocked": True,
        "blocked_reason": reason,
        "executor_start_allowed": False,
        "task_execution_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
    }


def build_runtime_executor_binding_heartbeat_projection(
    binding_record: dict[str, Any] | None,
) -> dict[str, Any]:
    binding = _as_mapping(binding_record)
    return {
        "projection": "runtime_executor_binding_heartbeat",
        "projection_only": True,
        "executor_binding_id": binding.get("executor_binding_id"),
        "runtime_session_id": binding.get("runtime_session_id"),
        "execution_lease_id": binding.get("execution_lease_id"),
        "capability_grant_id": binding.get("capability_grant_id"),
        "executor_id": binding.get("executor_id"),
        "executor_type": binding.get("executor_type"),
        "binding_status": binding.get("binding_status", "detached"),
        "heartbeat_live": False,
        "executor_enabled": False,
        "background_loop_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "io_allowed": False,
        "autonomy_allowed": False,
    }


def build_runtime_executor_binding_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_executor_binding_request(request)
    binding = validation["executor_binding_record"]

    return {
        "audit_schema": RUNTIME_EXECUTOR_BINDING_SCHEMA + ".audit",
        "decision": "reserved_runtime_executor_binding_record_only",
        "binding_request_id": validation.get("binding_request_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "request_valid": validation["valid"],
        "binding_created": validation["binding_created"],
        "executor_binding_record": binding,
        "heartbeat_projection": build_runtime_executor_binding_heartbeat_projection(
            binding
        ),
        "executor_enabled": False,
        "executor_started": False,
        "task_executed": False,
        "subprocess_started": False,
        "file_mutation_performed": False,
        "io_performed": False,
        "tool_call_performed": False,
        "autonomy_started": False,
        "self_start_performed": False,
        "background_loop_started": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
        "non_mainline_issues": validation["problems"],
    }


def build_runtime_executor_binding_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_executor_binding_audit_record(request)

    return {
        "seal": "runtime_executor_binding_bundle",
        "schema": RUNTIME_EXECUTOR_BINDING_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_EXECUTOR_OWNERSHIP_RECORD_ONLY_ZERO_EXECUTION",
        "next_package": 1241,
        "binding_request_id": audit.get("binding_request_id"),
        "runtime_session_id": audit.get("runtime_session_id"),
        "execution_lease_id": audit.get("execution_lease_id"),
        "capability_grant_id": audit.get("capability_grant_id"),
        "binding_created": audit["binding_created"],
        "audit_decision": audit["decision"],
        "executor_enabled": False,
        "executor_started": False,
        "task_executed": False,
        "subprocess_started": False,
        "file_mutation_performed": False,
        "io_performed": False,
        "tool_call_performed": False,
        "autonomy_started": False,
        "self_start_performed": False,
        "background_loop_started": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "all_execution_surfaces_locked": True,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


__all__ = [
    "RUNTIME_EXECUTOR_BINDING_SCHEMA",
    "AUTHORIZED_EXECUTOR_BIND_DECISION",
    "EXECUTOR_BINDING_STATES",
    "EXECUTOR_TYPES",
    "REQUIRED_EXECUTOR_BINDING_FIELDS",
    "EXECUTOR_BINDING_BOUNDARY_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_runtime_executor_binding_request",
    "validate_runtime_executor_binding_request",
    "build_runtime_executor_binding_record",
    "expire_runtime_executor_binding",
    "revoke_runtime_executor_binding",
    "can_runtime_executor_binding_authorize_execution",
    "build_runtime_executor_binding_heartbeat_projection",
    "build_runtime_executor_binding_audit_record",
    "build_runtime_executor_binding_milestone_seal",
]
