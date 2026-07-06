from __future__ import annotations

from copy import deepcopy
from typing import Any


RUNTIME_EXECUTION_LEASE_SCHEMA = "zero.runtime.execution_lease.v1"

AUTHORIZED_LEASE_DECISION = "AUTHORIZE_LIMITED_EXECUTION_LEASE_RECORD_ONLY"

LEASE_STATUSES = ("inactive", "granted", "expired", "revoked")

REQUIRED_EXECUTION_LEASE_FIELDS = (
    "lease_request_id",
    "runtime_session",
    "authorization_input",
    "lease_owner",
    "expiration_model",
    "revocation_model",
    "heartbeat_projection",
    "audit_required",
)

LEASE_BOUNDARY_LOCKS = {
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
    "runtime_session_required",
    "valid_runtime_session_id_required",
    "explicit_authorization_required",
    "active_session_state_required",
    "lease_record_only",
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
    return [field for field in REQUIRED_EXECUTION_LEASE_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in LEASE_BOUNDARY_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _lease_id(lease_request_id: str, runtime_session_id: str) -> str:
    return f"execution-lease::{runtime_session_id}::{lease_request_id}"


def build_runtime_execution_lease_request(
    *,
    lease_request_id: str,
    runtime_session: dict[str, Any] | None = None,
    authorization_input: dict[str, Any] | None = None,
    lease_owner: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_EXECUTION_LEASE_SCHEMA,
        "lease_request_id": lease_request_id,
        "runtime_session": deepcopy(runtime_session) if runtime_session is not None else {},
        "authorization_input": (
            deepcopy(authorization_input)
            if authorization_input is not None
            else {
                "decision": "NO_GO",
                "explicit_authorization": False,
                "authorize_lease_record": False,
            }
        ),
        "lease_owner": (
            deepcopy(lease_owner)
            if lease_owner is not None
            else {
                "operator_id": None,
                "executor_id": None,
                "ownership_verified": False,
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
        "heartbeat_projection": {
            "projection_only": True,
            "heartbeat_live": False,
            "lease_status": "inactive",
            "background_loop_allowed": False,
        },
        "boundary_locks": deepcopy(LEASE_BOUNDARY_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def validate_runtime_execution_lease_request(request: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    session = _as_mapping(record.get("runtime_session"))
    authorization = _as_mapping(record.get("authorization_input"))

    session_id = session.get("runtime_session_id")
    active_session_state = session.get("status") in {"born_inert", "active_inert"}
    valid_session = bool(session_id) and session.get("session_type") == "limited"
    authorized = (
        authorization.get("decision") == AUTHORIZED_LEASE_DECISION
        and authorization.get("explicit_authorization") is True
        and authorization.get("authorize_lease_record") is True
    )

    problems: list[str] = []
    if missing:
        problems.append("missing_required_fields")
    if missing_blockers:
        problems.append("missing_required_blockers")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if not valid_session:
        problems.append("invalid_runtime_session")
    if not active_session_state:
        problems.append("inactive_runtime_session_state")
    if not authorized:
        problems.append("lease_authorization_missing")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")

    lease_record = (
        build_runtime_execution_lease_record(record)
        if not problems
        else None
    )

    return {
        "schema": RUNTIME_EXECUTION_LEASE_SCHEMA,
        "valid": not problems,
        "lease_request_id": record.get("lease_request_id"),
        "runtime_session_id": session_id,
        "status": "accepted_execution_lease_record_request"
        if not problems
        else "blocked",
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "lease_created": lease_record is not None,
        "lease_record": lease_record,
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


def build_runtime_execution_lease_record(request: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(request)
    session = _as_mapping(record.get("runtime_session"))
    session_id = str(session.get("runtime_session_id"))
    lease_request_id = str(record.get("lease_request_id"))

    return {
        "lease_id": _lease_id(lease_request_id, session_id),
        "runtime_session_id": session_id,
        "lease_status": "granted",
        "allowed_statuses": list(LEASE_STATUSES),
        "lease_owner": _as_mapping(record.get("lease_owner")),
        "expiration_model": _as_mapping(record.get("expiration_model")),
        "revocation_model": _as_mapping(record.get("revocation_model")),
        "record_only": True,
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


def expire_runtime_execution_lease(
    lease_record: dict[str, Any],
    *,
    current_tick: int,
) -> dict[str, Any]:
    lease = _as_mapping(lease_record)
    expiration = _as_mapping(lease.get("expiration_model"))
    expires_at = expiration.get("expires_at_tick", 0)
    expired = current_tick >= expires_at
    expiration["current_tick"] = current_tick
    expiration["expired"] = expired

    if expired:
        lease["lease_status"] = "expired"
    lease["expiration_model"] = expiration
    lease["execution_allowed"] = False
    lease["task_execution_allowed"] = False
    return lease


def revoke_runtime_execution_lease(
    lease_record: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    lease = _as_mapping(lease_record)
    revocation = _as_mapping(lease.get("revocation_model"))
    revocation["revoked"] = True
    revocation["revocation_reason"] = reason
    lease["revocation_model"] = revocation
    lease["lease_status"] = "revoked"
    lease["execution_allowed"] = False
    lease["task_execution_allowed"] = False
    return lease


def can_runtime_execution_lease_authorize_execution(
    lease_record: dict[str, Any],
) -> dict[str, Any]:
    lease = _as_mapping(lease_record)
    active = lease.get("lease_status") == "granted"
    blocked_reason = None
    if lease.get("lease_status") == "expired":
        blocked_reason = "lease_expired"
    elif lease.get("lease_status") == "revoked":
        blocked_reason = "lease_revoked"
    elif not active:
        blocked_reason = "lease_not_granted"

    return {
        "lease_id": lease.get("lease_id"),
        "lease_status": lease.get("lease_status", "inactive"),
        "can_authorize_execution": False,
        "blocked": True,
        "blocked_reason": blocked_reason or "execution_capability_not_granted",
        "executor_start_allowed": False,
        "task_execution_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
    }


def build_runtime_execution_lease_heartbeat_projection(
    lease_record: dict[str, Any] | None,
) -> dict[str, Any]:
    lease = _as_mapping(lease_record)
    return {
        "projection": "runtime_execution_lease_heartbeat",
        "projection_only": True,
        "lease_id": lease.get("lease_id"),
        "runtime_session_id": lease.get("runtime_session_id"),
        "lease_status": lease.get("lease_status", "inactive"),
        "heartbeat_live": False,
        "background_loop_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "io_allowed": False,
        "autonomy_allowed": False,
    }


def build_runtime_execution_lease_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_execution_lease_request(request)
    lease = validation["lease_record"]

    return {
        "audit_schema": RUNTIME_EXECUTION_LEASE_SCHEMA + ".audit",
        "decision": "reserved_runtime_execution_lease_record_only",
        "lease_request_id": validation.get("lease_request_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "request_valid": validation["valid"],
        "lease_created": validation["lease_created"],
        "lease_record": lease,
        "heartbeat_projection": build_runtime_execution_lease_heartbeat_projection(lease),
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


def build_runtime_execution_lease_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_execution_lease_audit_record(request)

    return {
        "seal": "runtime_execution_lease_bundle",
        "schema": RUNTIME_EXECUTION_LEASE_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_CONTROLLED_LEASE_RECORD_ONLY_ZERO_EXECUTION_CAPABILITY",
        "next_package": 1225,
        "lease_request_id": audit.get("lease_request_id"),
        "runtime_session_id": audit.get("runtime_session_id"),
        "lease_created": audit["lease_created"],
        "audit_decision": audit["decision"],
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
    "RUNTIME_EXECUTION_LEASE_SCHEMA",
    "AUTHORIZED_LEASE_DECISION",
    "LEASE_STATUSES",
    "REQUIRED_EXECUTION_LEASE_FIELDS",
    "LEASE_BOUNDARY_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_runtime_execution_lease_request",
    "validate_runtime_execution_lease_request",
    "build_runtime_execution_lease_record",
    "expire_runtime_execution_lease",
    "revoke_runtime_execution_lease",
    "can_runtime_execution_lease_authorize_execution",
    "build_runtime_execution_lease_heartbeat_projection",
    "build_runtime_execution_lease_audit_record",
    "build_runtime_execution_lease_milestone_seal",
]
