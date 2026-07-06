from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_EXECUTOR_INVOCATION_BOUNDARY_SCHEMA = (
    "zero.runtime.executor_invocation_boundary.v1"
)

EXECUTOR_INVOCATION_BOUNDARY_STATUSES = ("bounded", "denied", "expired", "revoked")

REQUIRED_EXECUTOR_INVOCATION_BOUNDARY_FIELDS = (
    "executor_invocation_request_id",
    "dispatch_commit",
    "runtime_session_id",
    "execution_lease",
    "capability_grant",
    "executor_binding",
    "audit_required",
)

EXECUTOR_INVOCATION_BOUNDARY_LOCKS = {
    "executor_run_allowed": False,
    "task_execution_allowed": False,
    "tool_invocation_allowed": False,
    "subprocess_allowed": False,
    "shell_allowed": False,
    "network_allowed": False,
    "filesystem_mutation_allowed": False,
    "state_mutation_allowed": False,
    "task_completion_allowed": False,
    "autonomy_loop_allowed": False,
    "background_worker_allowed": False,
}


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [
        field
        for field in REQUIRED_EXECUTOR_INVOCATION_BOUNDARY_FIELDS
        if field not in record
    ]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in EXECUTOR_INVOCATION_BOUNDARY_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _executor_invocation_id(
    *,
    request_id: str,
    dispatch_commit_id: str,
    dispatch_id: str,
    executor_binding_id: str,
    runtime_session_id: str,
) -> str:
    fragment = _stable_fragment(
        {
            "request_id": request_id,
            "dispatch_commit_id": dispatch_commit_id,
            "dispatch_id": dispatch_id,
            "executor_binding_id": executor_binding_id,
            "runtime_session_id": runtime_session_id,
        }
    )
    return (
        f"executor-invocation-boundary::{runtime_session_id}::"
        f"{dispatch_commit_id}::{fragment}"
    )


def build_runtime_executor_invocation_boundary_request(
    *,
    executor_invocation_request_id: str,
    dispatch_commit: dict[str, Any] | None = None,
    runtime_session_id: str | None = None,
    execution_lease: dict[str, Any] | None = None,
    capability_grant: dict[str, Any] | None = None,
    executor_binding: dict[str, Any] | None = None,
    invocation_reason: str = "explicit_executor_invocation_boundary_authorization",
    invocation_time: str = "deterministic-time::1337",
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_EXECUTOR_INVOCATION_BOUNDARY_SCHEMA,
        "executor_invocation_request_id": executor_invocation_request_id,
        "dispatch_commit": _as_mapping(dispatch_commit),
        "runtime_session_id": runtime_session_id,
        "execution_lease": _as_mapping(execution_lease),
        "capability_grant": _as_mapping(capability_grant),
        "executor_binding": _as_mapping(executor_binding),
        "invocation_reason": invocation_reason,
        "invocation_time": invocation_time,
        "boundary_locks": deepcopy(EXECUTOR_INVOCATION_BOUNDARY_LOCKS),
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


def _evaluate_executor_invocation_boundary_request(
    record: dict[str, Any],
) -> dict[str, Any]:
    commit = _as_mapping(record.get("dispatch_commit"))
    lease = _as_mapping(record.get("execution_lease"))
    grant = _as_mapping(record.get("capability_grant"))
    binding = _as_mapping(record.get("executor_binding"))
    executor_target = _as_mapping(commit.get("executor_target"))

    runtime_session_id = record.get("runtime_session_id")
    dispatch_commit_id = commit.get("dispatch_commit_id")
    dispatch_id = commit.get("dispatch_id")
    task_admission_id = commit.get("task_admission_id")
    execution_lease_id = lease.get("lease_id") or commit.get("execution_lease_id")
    capability_grant_id = grant.get("capability_grant_id") or commit.get(
        "capability_grant_id"
    )
    executor_binding_id = binding.get("executor_binding_id") or commit.get(
        "executor_binding_id"
    )

    committed = (
        bool(dispatch_commit_id)
        and commit.get("commit_status") == "committed"
        and commit.get("dispatch_ready") is True
        and commit.get("record_only") is True
        and commit.get("executor_run_performed") is False
        and commit.get("tool_invoked") is False
        and commit.get("state_mutation_performed") is False
        and commit.get("task_completed") is False
    )
    active_lease = (
        bool(execution_lease_id)
        and lease.get("lease_id") == execution_lease_id
        and lease.get("runtime_session_id") == runtime_session_id
        and lease.get("lease_status") == "granted"
    )
    active_grant = (
        bool(capability_grant_id)
        and grant.get("capability_grant_id") == capability_grant_id
        and grant.get("owner_session_id") == runtime_session_id
        and grant.get("owner_lease_id") == execution_lease_id
        and grant.get("grant_status") == "granted"
    )
    active_binding = (
        bool(executor_binding_id)
        and binding.get("executor_binding_id") == executor_binding_id
        and binding.get("runtime_session_id") == runtime_session_id
        and binding.get("execution_lease_id") == execution_lease_id
        and binding.get("capability_grant_id") == capability_grant_id
        and binding.get("binding_status") == "bound"
    )
    target_matches_binding = (
        bool(executor_target)
        and executor_target.get("executor_binding_id") == executor_binding_id
        and executor_target.get("runtime_session_id") == runtime_session_id
        and executor_target.get("execution_lease_id") == execution_lease_id
        and executor_target.get("capability_grant_id") == capability_grant_id
        and executor_target.get("target_mode") == "record_only"
    )

    problems: list[str] = []
    if not dispatch_commit_id:
        problems.append("missing_dispatch_commit")
    elif not committed:
        problems.append("dispatch_commit_not_committed")
    if commit.get("commit_status") == "denied":
        problems.append("denied_dispatch_commit")
    if commit.get("commit_status") == "expired":
        problems.append("expired_dispatch_commit")
    if commit.get("commit_status") == "revoked":
        problems.append("revoked_dispatch_commit")
    if not runtime_session_id:
        problems.append("invalid_runtime_session_id")
    if not dispatch_id:
        problems.append("missing_dispatch_id")
    if not task_admission_id:
        problems.append("missing_task_admission_id")
    if commit and commit.get("runtime_session_id") != runtime_session_id:
        problems.append("dispatch_commit_session_mismatch")
    if commit and commit.get("execution_lease_id") != execution_lease_id:
        problems.append("dispatch_commit_lease_mismatch")
    if commit and commit.get("capability_grant_id") != capability_grant_id:
        problems.append("dispatch_commit_capability_mismatch")
    if commit and commit.get("executor_binding_id") != executor_binding_id:
        problems.append("dispatch_commit_executor_binding_mismatch")
    if not executor_target:
        problems.append("missing_executor_target")
    elif not target_matches_binding:
        problems.append("executor_target_mismatch")
    if not active_lease:
        problems.append("inactive_execution_lease")
    if lease.get("lease_status") == "expired":
        problems.append("expired_execution_lease")
    if lease.get("lease_status") == "revoked":
        problems.append("revoked_execution_lease")
    if not active_grant:
        problems.append("inactive_capability_grant")
    if grant.get("grant_status") == "revoked":
        problems.append("revoked_capability_grant")
    if grant.get("grant_status") == "expired":
        problems.append("expired_capability_grant")
    if not active_binding:
        problems.append("inactive_executor_binding")
    if not binding:
        problems.append("missing_executor_binding")
    if binding.get("binding_status") == "revoked":
        problems.append("revoked_executor_binding")
    if binding.get("binding_status") == "expired":
        problems.append("expired_executor_binding")

    return {
        "dispatch_commit_id": dispatch_commit_id,
        "dispatch_id": dispatch_id,
        "task_admission_id": task_admission_id,
        "runtime_session_id": runtime_session_id,
        "execution_lease_id": execution_lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "executor_target": executor_target,
        "problems": problems,
    }


def validate_runtime_executor_invocation_boundary_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_executor_invocation_boundary_request(record)
    problems = list(dict.fromkeys(evaluation["problems"]))
    if missing:
        problems.append("missing_required_fields")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")

    status = "bounded" if not problems else "denied"
    return {
        "schema": RUNTIME_EXECUTOR_INVOCATION_BOUNDARY_SCHEMA,
        "valid": not problems,
        "executor_invocation_request_id": record.get("executor_invocation_request_id"),
        "dispatch_commit_id": evaluation["dispatch_commit_id"],
        "dispatch_id": evaluation["dispatch_id"],
        "task_admission_id": evaluation["task_admission_id"],
        "runtime_session_id": evaluation["runtime_session_id"],
        "execution_lease_id": evaluation["execution_lease_id"],
        "capability_grant_id": evaluation["capability_grant_id"],
        "executor_binding_id": evaluation["executor_binding_id"],
        "executor_target": evaluation["executor_target"],
        "invocation_status": status,
        "boundary_ready": not problems,
        "denial_reason": "none" if not problems else ";".join(problems),
        "problems": problems,
        "missing_required_fields": missing,
        "unlock_attempts": unlocks,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
    }


def _build_invocation_envelope(validation: dict[str, Any]) -> dict[str, Any]:
    target = _as_mapping(validation.get("executor_target"))
    return {
        "envelope_type": "executor_invocation_boundary_record_only",
        "runtime_session_id": validation.get("runtime_session_id"),
        "dispatch_commit_id": validation.get("dispatch_commit_id"),
        "dispatch_id": validation.get("dispatch_id"),
        "task_admission_id": validation.get("task_admission_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "executor_id": target.get("executor_id"),
        "executor_type": target.get("executor_type"),
        "target_mode": "record_only",
        "executor_run_allowed": False,
        "task_execution_allowed": False,
        "tool_invocation_allowed": False,
        "subprocess_allowed": False,
        "shell_allowed": False,
        "network_allowed": False,
        "filesystem_mutation_allowed": False,
        "state_mutation_allowed": False,
        "task_completion_allowed": False,
        "autonomy_loop_allowed": False,
        "background_worker_allowed": False,
    }


def build_runtime_executor_invocation_boundary_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_executor_invocation_boundary_request(request)
    record = _as_mapping(request)
    executor_invocation_id = _executor_invocation_id(
        request_id=str(validation.get("executor_invocation_request_id")),
        dispatch_commit_id=str(validation.get("dispatch_commit_id")),
        dispatch_id=str(validation.get("dispatch_id")),
        executor_binding_id=str(validation.get("executor_binding_id")),
        runtime_session_id=str(validation.get("runtime_session_id")),
    )
    boundary = {
        "executor_invocation_id": executor_invocation_id,
        "dispatch_commit_id": validation.get("dispatch_commit_id"),
        "dispatch_id": validation.get("dispatch_id"),
        "task_admission_id": validation.get("task_admission_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "executor_target": _as_mapping(validation.get("executor_target")),
        "invocation_envelope": _build_invocation_envelope(validation),
        "invocation_status": validation["invocation_status"],
        "invocation_reason": record.get("invocation_reason"),
        "invocation_time": record.get("invocation_time"),
        "denial_reason": validation["denial_reason"],
        "audit_record": {},
        "supported_statuses": list(EXECUTOR_INVOCATION_BOUNDARY_STATUSES),
        "record_only": True,
        "boundary_ready": validation["invocation_status"] == "bounded",
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
    }
    boundary["audit_record"] = build_runtime_executor_invocation_boundary_audit_projection(
        boundary
    )
    return boundary


def expire_runtime_executor_invocation_boundary(
    boundary_record: dict[str, Any],
    *,
    reason: str = "executor_invocation_boundary_expired",
) -> dict[str, Any]:
    boundary = _as_mapping(boundary_record)
    boundary["invocation_status"] = "expired"
    boundary["boundary_ready"] = False
    boundary["denial_reason"] = reason
    boundary["executor_run_performed"] = False
    boundary["task_execution_performed"] = False
    boundary["audit_record"] = build_runtime_executor_invocation_boundary_audit_projection(
        boundary
    )
    return boundary


def revoke_runtime_executor_invocation_boundary(
    boundary_record: dict[str, Any],
    *,
    reason: str = "executor_invocation_boundary_revoked",
) -> dict[str, Any]:
    boundary = _as_mapping(boundary_record)
    boundary["invocation_status"] = "revoked"
    boundary["boundary_ready"] = False
    boundary["denial_reason"] = reason
    boundary["executor_run_performed"] = False
    boundary["task_execution_performed"] = False
    boundary["audit_record"] = build_runtime_executor_invocation_boundary_audit_projection(
        boundary
    )
    return boundary


def can_runtime_executor_invocation_boundary_run(
    boundary_record: dict[str, Any],
) -> dict[str, Any]:
    boundary = _as_mapping(boundary_record)
    return {
        "executor_invocation_id": boundary.get("executor_invocation_id"),
        "dispatch_commit_id": boundary.get("dispatch_commit_id"),
        "invocation_status": boundary.get("invocation_status", "denied"),
        "can_run_executor": False,
        "can_execute_task": False,
        "blocked": True,
        "blocked_reason": "runtime_executor_invocation_execution_disabled",
        "executor_run_allowed": False,
        "task_execution_allowed": False,
        "tool_invocation_allowed": False,
        "subprocess_allowed": False,
        "shell_allowed": False,
        "network_allowed": False,
        "filesystem_mutation_allowed": False,
        "state_mutation_allowed": False,
        "task_completion_allowed": False,
        "autonomy_loop_allowed": False,
        "background_worker_allowed": False,
    }


def build_runtime_executor_invocation_boundary_audit_projection(
    boundary_record: dict[str, Any] | None,
) -> dict[str, Any]:
    boundary = _as_mapping(boundary_record)
    return {
        "projection": "runtime_executor_invocation_boundary_audit",
        "projection_only": True,
        "executor_invocation_id": boundary.get("executor_invocation_id"),
        "dispatch_commit_id": boundary.get("dispatch_commit_id"),
        "dispatch_id": boundary.get("dispatch_id"),
        "task_admission_id": boundary.get("task_admission_id"),
        "executor_binding_id": boundary.get("executor_binding_id"),
        "invocation_status": boundary.get("invocation_status", "denied"),
        "denial_reason": boundary.get("denial_reason", "not_evaluated"),
        "invocation_time": boundary.get("invocation_time"),
        "executor_target": _as_mapping(boundary.get("executor_target")),
        "invocation_envelope": _as_mapping(boundary.get("invocation_envelope")),
        "bounded_record_only": boundary.get("invocation_status") == "bounded",
        "boundary_ready": boundary.get("invocation_status") == "bounded",
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
    }


def build_runtime_executor_invocation_boundary_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_executor_invocation_boundary_request(request)
    boundary = build_runtime_executor_invocation_boundary_record(request)
    return {
        "audit_schema": RUNTIME_EXECUTOR_INVOCATION_BOUNDARY_SCHEMA + ".audit",
        "decision": "reserved_runtime_executor_invocation_boundary_record_only",
        "executor_invocation_request_id": validation.get(
            "executor_invocation_request_id"
        ),
        "dispatch_commit_id": validation.get("dispatch_commit_id"),
        "dispatch_id": validation.get("dispatch_id"),
        "task_admission_id": validation.get("task_admission_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "request_valid": validation["valid"],
        "executor_invocation_boundary_record": boundary,
        "audit_projection": boundary["audit_record"],
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
        "non_mainline_issues": validation["problems"],
    }


def build_runtime_executor_invocation_boundary_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_executor_invocation_boundary_audit_record(request)
    boundary = _as_mapping(audit.get("executor_invocation_boundary_record"))
    return {
        "seal": "runtime_executor_invocation_boundary_bundle",
        "schema": RUNTIME_EXECUTOR_INVOCATION_BOUNDARY_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_EXECUTOR_INVOCATION_BOUNDARY_RECORDS_ONLY_NO_EXECUTION",
        "executor_invocation_id": boundary.get("executor_invocation_id"),
        "dispatch_commit_id": boundary.get("dispatch_commit_id"),
        "dispatch_id": boundary.get("dispatch_id"),
        "task_admission_id": boundary.get("task_admission_id"),
        "invocation_status": boundary.get("invocation_status"),
        "audit_decision": audit["decision"],
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
        "forbidden_surfaces_locked": True,
        "audit_required": True,
    }


__all__ = [
    "RUNTIME_EXECUTOR_INVOCATION_BOUNDARY_SCHEMA",
    "EXECUTOR_INVOCATION_BOUNDARY_STATUSES",
    "REQUIRED_EXECUTOR_INVOCATION_BOUNDARY_FIELDS",
    "EXECUTOR_INVOCATION_BOUNDARY_LOCKS",
    "build_runtime_executor_invocation_boundary_request",
    "validate_runtime_executor_invocation_boundary_request",
    "build_runtime_executor_invocation_boundary_record",
    "expire_runtime_executor_invocation_boundary",
    "revoke_runtime_executor_invocation_boundary",
    "can_runtime_executor_invocation_boundary_run",
    "build_runtime_executor_invocation_boundary_audit_projection",
    "build_runtime_executor_invocation_boundary_audit_record",
    "build_runtime_executor_invocation_boundary_milestone_seal",
]
