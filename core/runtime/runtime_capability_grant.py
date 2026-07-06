from __future__ import annotations

from copy import deepcopy
from typing import Any


RUNTIME_CAPABILITY_GRANT_SCHEMA = "zero.runtime.capability_grant.v1"

AUTHORIZED_CAPABILITY_GRANT_DECISION = "AUTHORIZE_CAPABILITY_GRANT_RECORD_ONLY"

CAPABILITY_STATES = ("none", "granted", "revoked", "expired")

CAPABILITY_CATEGORIES = (
    "read_access",
    "write_access",
    "tool_access",
    "execution_access",
    "mutation_access",
    "network_access",
)

REQUIRED_CAPABILITY_GRANT_FIELDS = (
    "capability_request_id",
    "runtime_session_id",
    "execution_lease",
    "authorization_input",
    "requested_capabilities",
    "expiration_model",
    "revocation_model",
    "audit_required",
)

CAPABILITY_GRANT_BOUNDARY_LOCKS = {
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
    "network_access_allowed": False,
}

REQUIRED_BLOCKERS = (
    "runtime_session_id_required",
    "active_execution_lease_required",
    "explicit_authorization_required",
    "capability_grant_record_only",
    "all_capabilities_default_false",
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
    return [field for field in REQUIRED_CAPABILITY_GRANT_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in CAPABILITY_GRANT_BOUNDARY_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _empty_capabilities() -> dict[str, bool]:
    return {category: False for category in CAPABILITY_CATEGORIES}


def _grant_id(capability_request_id: str, session_id: str, lease_id: str) -> str:
    return f"capability-grant::{session_id}::{lease_id}::{capability_request_id}"


def build_runtime_capability_grant_request(
    *,
    capability_request_id: str,
    runtime_session_id: str | None = None,
    execution_lease: dict[str, Any] | None = None,
    authorization_input: dict[str, Any] | None = None,
    requested_capabilities: dict[str, bool] | None = None,
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_CAPABILITY_GRANT_SCHEMA,
        "capability_request_id": capability_request_id,
        "runtime_session_id": runtime_session_id,
        "execution_lease": (
            deepcopy(execution_lease) if execution_lease is not None else {}
        ),
        "authorization_input": (
            deepcopy(authorization_input)
            if authorization_input is not None
            else {
                "decision": "NO_GO",
                "explicit_authorization": False,
                "authorize_capability_record": False,
            }
        ),
        "requested_capabilities": (
            deepcopy(requested_capabilities)
            if requested_capabilities is not None
            else _empty_capabilities()
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
        "boundary_locks": deepcopy(CAPABILITY_GRANT_BOUNDARY_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def validate_runtime_capability_grant_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    session_id = record.get("runtime_session_id")
    lease = _as_mapping(record.get("execution_lease"))
    authorization = _as_mapping(record.get("authorization_input"))

    lease_id = lease.get("lease_id")
    active_lease = (
        bool(lease_id)
        and lease.get("runtime_session_id") == session_id
        and lease.get("lease_status") == "granted"
    )
    authorized = (
        authorization.get("decision") == AUTHORIZED_CAPABILITY_GRANT_DECISION
        and authorization.get("explicit_authorization") is True
        and authorization.get("authorize_capability_record") is True
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
    if not authorized:
        problems.append("capability_authorization_missing")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")

    grant_record = (
        build_runtime_capability_grant_record(record)
        if not problems
        else None
    )

    return {
        "schema": RUNTIME_CAPABILITY_GRANT_SCHEMA,
        "valid": not problems,
        "capability_request_id": record.get("capability_request_id"),
        "runtime_session_id": session_id,
        "execution_lease_id": lease_id,
        "status": "accepted_capability_grant_record_request"
        if not problems
        else "blocked",
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "grant_created": grant_record is not None,
        "capability_grant_record": grant_record,
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


def build_runtime_capability_grant_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    lease = _as_mapping(record.get("execution_lease"))
    session_id = str(record.get("runtime_session_id"))
    lease_id = str(lease.get("lease_id"))
    request_id = str(record.get("capability_request_id"))
    requested = _as_mapping(record.get("requested_capabilities"))

    granted = {
        category: bool(requested.get(category, False))
        for category in CAPABILITY_CATEGORIES
    }
    denied = {
        category: not granted[category]
        for category in CAPABILITY_CATEGORIES
    }

    return {
        "capability_grant_id": _grant_id(request_id, session_id, lease_id),
        "owner_session_id": session_id,
        "owner_lease_id": lease_id,
        "granted_capabilities": granted,
        "denied_capabilities": denied,
        "grant_status": "granted",
        "supported_states": list(CAPABILITY_STATES),
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


def expire_runtime_capability_grant(
    grant_record: dict[str, Any],
    *,
    current_tick: int,
) -> dict[str, Any]:
    grant = _as_mapping(grant_record)
    expiration = _as_mapping(grant.get("expiration_model"))
    expires_at = expiration.get("expires_at_tick", 0)
    expired = current_tick >= expires_at
    expiration["current_tick"] = current_tick
    expiration["expired"] = expired
    if expired:
        grant["grant_status"] = "expired"
    grant["expiration_model"] = expiration
    grant["executor_start_allowed"] = False
    grant["execution_allowed"] = False
    return grant


def revoke_runtime_capability_grant(
    grant_record: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    grant = _as_mapping(grant_record)
    revocation = _as_mapping(grant.get("revocation_model"))
    revocation["revoked"] = True
    revocation["revocation_reason"] = reason
    grant["revocation_model"] = revocation
    grant["grant_status"] = "revoked"
    grant["executor_start_allowed"] = False
    grant["execution_allowed"] = False
    return grant


def can_runtime_capability_grant_authorize_executor(
    grant_record: dict[str, Any],
) -> dict[str, Any]:
    grant = _as_mapping(grant_record)
    status = grant.get("grant_status", "none")
    if status == "expired":
        reason = "capability_grant_expired"
    elif status == "revoked":
        reason = "capability_grant_revoked"
    elif status != "granted":
        reason = "capability_grant_not_granted"
    else:
        reason = "executor_detached"

    return {
        "capability_grant_id": grant.get("capability_grant_id"),
        "grant_status": status,
        "can_authorize_executor": False,
        "blocked": True,
        "blocked_reason": reason,
        "executor_start_allowed": False,
        "task_execution_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
    }


def build_runtime_capability_audit_projection(
    grant_record: dict[str, Any] | None,
) -> dict[str, Any]:
    grant = _as_mapping(grant_record)
    return {
        "projection": "runtime_capability_grant_audit",
        "projection_only": True,
        "capability_grant_id": grant.get("capability_grant_id"),
        "owner_session_id": grant.get("owner_session_id"),
        "owner_lease_id": grant.get("owner_lease_id"),
        "grant_status": grant.get("grant_status", "none"),
        "granted_capabilities": grant.get("granted_capabilities", _empty_capabilities()),
        "executor_start_allowed": False,
        "execution_allowed": False,
        "mutation_allowed": False,
        "tool_call_allowed": False,
        "io_allowed": False,
        "background_loop_allowed": False,
    }


def build_runtime_capability_grant_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_capability_grant_request(request)
    grant = validation["capability_grant_record"]

    return {
        "audit_schema": RUNTIME_CAPABILITY_GRANT_SCHEMA + ".audit",
        "decision": "reserved_runtime_capability_grant_record_only",
        "capability_request_id": validation.get("capability_request_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "request_valid": validation["valid"],
        "grant_created": validation["grant_created"],
        "capability_grant_record": grant,
        "capability_audit_projection": build_runtime_capability_audit_projection(grant),
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


def build_runtime_capability_grant_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_capability_grant_audit_record(request)

    return {
        "seal": "runtime_capability_grant_bundle",
        "schema": RUNTIME_CAPABILITY_GRANT_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_PERMISSION_MODEL_ONLY_EXECUTOR_REMAINS_DETACHED",
        "next_package": 1233,
        "capability_request_id": audit.get("capability_request_id"),
        "runtime_session_id": audit.get("runtime_session_id"),
        "execution_lease_id": audit.get("execution_lease_id"),
        "grant_created": audit["grant_created"],
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
    "RUNTIME_CAPABILITY_GRANT_SCHEMA",
    "AUTHORIZED_CAPABILITY_GRANT_DECISION",
    "CAPABILITY_STATES",
    "CAPABILITY_CATEGORIES",
    "REQUIRED_CAPABILITY_GRANT_FIELDS",
    "CAPABILITY_GRANT_BOUNDARY_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_runtime_capability_grant_request",
    "validate_runtime_capability_grant_request",
    "build_runtime_capability_grant_record",
    "expire_runtime_capability_grant",
    "revoke_runtime_capability_grant",
    "can_runtime_capability_grant_authorize_executor",
    "build_runtime_capability_audit_projection",
    "build_runtime_capability_grant_audit_record",
    "build_runtime_capability_grant_milestone_seal",
]
