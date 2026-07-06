from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_TASK_DISPATCH_COMMIT_SCHEMA = "zero.runtime.task_dispatch_commit.v1"

DISPATCH_COMMIT_STATUSES = ("committed", "denied", "expired", "revoked")

REQUIRED_DISPATCH_COMMIT_FIELDS = (
    "dispatch_commit_request_id",
    "dispatch_preparation",
    "runtime_session_id",
    "execution_lease",
    "capability_grant",
    "executor_binding",
    "audit_required",
)

DISPATCH_COMMIT_LOCKS = {
    "executor_run_allowed": False,
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
    return [field for field in REQUIRED_DISPATCH_COMMIT_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in DISPATCH_COMMIT_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _dispatch_commit_id(
    *,
    request_id: str,
    dispatch_id: str,
    task_admission_id: str,
    executor_binding_id: str,
    runtime_session_id: str,
) -> str:
    fragment = _stable_fragment(
        {
            "request_id": request_id,
            "dispatch_id": dispatch_id,
            "task_admission_id": task_admission_id,
            "executor_binding_id": executor_binding_id,
            "runtime_session_id": runtime_session_id,
        }
    )
    return f"task-dispatch-commit::{runtime_session_id}::{dispatch_id}::{fragment}"


def build_runtime_task_dispatch_commit_request(
    *,
    dispatch_commit_request_id: str,
    dispatch_preparation: dict[str, Any] | None = None,
    runtime_session_id: str | None = None,
    execution_lease: dict[str, Any] | None = None,
    capability_grant: dict[str, Any] | None = None,
    executor_binding: dict[str, Any] | None = None,
    commit_reason: str = "explicit_dispatch_commit_authorization",
    commit_time: str = "deterministic-time::1329",
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_TASK_DISPATCH_COMMIT_SCHEMA,
        "dispatch_commit_request_id": dispatch_commit_request_id,
        "dispatch_preparation": _as_mapping(dispatch_preparation),
        "runtime_session_id": runtime_session_id,
        "execution_lease": _as_mapping(execution_lease),
        "capability_grant": _as_mapping(capability_grant),
        "executor_binding": _as_mapping(executor_binding),
        "commit_reason": commit_reason,
        "commit_time": commit_time,
        "boundary_locks": deepcopy(DISPATCH_COMMIT_LOCKS),
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


def _evaluate_dispatch_commit_request(record: dict[str, Any]) -> dict[str, Any]:
    dispatch = _as_mapping(record.get("dispatch_preparation"))
    lease = _as_mapping(record.get("execution_lease"))
    grant = _as_mapping(record.get("capability_grant"))
    binding = _as_mapping(record.get("executor_binding"))
    executor_target = _as_mapping(dispatch.get("executor_target"))

    runtime_session_id = record.get("runtime_session_id")
    dispatch_id = dispatch.get("dispatch_id")
    task_admission_id = dispatch.get("task_admission_id")
    execution_lease_id = lease.get("lease_id") or executor_target.get(
        "execution_lease_id"
    )
    capability_grant_id = grant.get("capability_grant_id") or executor_target.get(
        "capability_grant_id"
    )
    executor_binding_id = binding.get("executor_binding_id") or dispatch.get(
        "executor_binding_id"
    )

    prepared = (
        bool(dispatch_id)
        and dispatch.get("dispatch_status") == "prepared"
        and dispatch.get("record_only") is True
        and dispatch.get("executor_run_performed") is False
        and dispatch.get("tool_invoked") is False
        and dispatch.get("state_mutation_performed") is False
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
    if not dispatch_id:
        problems.append("missing_dispatch_preparation")
    elif not prepared:
        problems.append("dispatch_preparation_not_prepared")
    if dispatch.get("dispatch_status") == "denied":
        problems.append("denied_dispatch_preparation")
    if dispatch.get("dispatch_status") == "expired":
        problems.append("expired_dispatch_preparation")
    if dispatch.get("dispatch_status") == "revoked":
        problems.append("revoked_dispatch_preparation")
    if not runtime_session_id:
        problems.append("invalid_runtime_session_id")
    if not task_admission_id:
        problems.append("missing_task_admission_id")
    if dispatch and dispatch.get("executor_binding_id") != executor_binding_id:
        problems.append("dispatch_executor_binding_mismatch")
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
        "dispatch_id": dispatch_id,
        "task_admission_id": task_admission_id,
        "runtime_session_id": runtime_session_id,
        "execution_lease_id": execution_lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "executor_target": executor_target,
        "problems": problems,
    }


def validate_runtime_task_dispatch_commit_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_dispatch_commit_request(record)
    problems = list(dict.fromkeys(evaluation["problems"]))
    if missing:
        problems.append("missing_required_fields")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")

    status = "committed" if not problems else "denied"
    return {
        "schema": RUNTIME_TASK_DISPATCH_COMMIT_SCHEMA,
        "valid": not problems,
        "dispatch_commit_request_id": record.get("dispatch_commit_request_id"),
        "dispatch_id": evaluation["dispatch_id"],
        "task_admission_id": evaluation["task_admission_id"],
        "runtime_session_id": evaluation["runtime_session_id"],
        "execution_lease_id": evaluation["execution_lease_id"],
        "capability_grant_id": evaluation["capability_grant_id"],
        "executor_binding_id": evaluation["executor_binding_id"],
        "executor_target": evaluation["executor_target"],
        "commit_status": status,
        "commit_allowed": not problems,
        "denial_reason": "none" if not problems else ";".join(problems),
        "problems": problems,
        "missing_required_fields": missing,
        "unlock_attempts": unlocks,
        "executor_run_performed": False,
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


def build_runtime_task_dispatch_commit_record(request: dict[str, Any]) -> dict[str, Any]:
    validation = validate_runtime_task_dispatch_commit_request(request)
    record = _as_mapping(request)
    dispatch_commit_id = _dispatch_commit_id(
        request_id=str(validation.get("dispatch_commit_request_id")),
        dispatch_id=str(validation.get("dispatch_id")),
        task_admission_id=str(validation.get("task_admission_id")),
        executor_binding_id=str(validation.get("executor_binding_id")),
        runtime_session_id=str(validation.get("runtime_session_id")),
    )
    commit = {
        "dispatch_commit_id": dispatch_commit_id,
        "dispatch_id": validation.get("dispatch_id"),
        "task_admission_id": validation.get("task_admission_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "executor_target": _as_mapping(validation.get("executor_target")),
        "commit_status": validation["commit_status"],
        "commit_reason": record.get("commit_reason"),
        "commit_time": record.get("commit_time"),
        "denial_reason": validation["denial_reason"],
        "audit_record": {},
        "supported_statuses": list(DISPATCH_COMMIT_STATUSES),
        "record_only": True,
        "dispatch_ready": validation["commit_status"] == "committed",
        "executor_run_performed": False,
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
    commit["audit_record"] = build_runtime_task_dispatch_commit_audit_projection(commit)
    return commit


def expire_runtime_task_dispatch_commit(
    commit_record: dict[str, Any],
    *,
    reason: str = "task_dispatch_commit_expired",
) -> dict[str, Any]:
    commit = _as_mapping(commit_record)
    commit["commit_status"] = "expired"
    commit["dispatch_ready"] = False
    commit["denial_reason"] = reason
    commit["executor_run_performed"] = False
    commit["audit_record"] = build_runtime_task_dispatch_commit_audit_projection(commit)
    return commit


def revoke_runtime_task_dispatch_commit(
    commit_record: dict[str, Any],
    *,
    reason: str = "task_dispatch_commit_revoked",
) -> dict[str, Any]:
    commit = _as_mapping(commit_record)
    commit["commit_status"] = "revoked"
    commit["dispatch_ready"] = False
    commit["denial_reason"] = reason
    commit["executor_run_performed"] = False
    commit["audit_record"] = build_runtime_task_dispatch_commit_audit_projection(commit)
    return commit


def can_runtime_task_dispatch_commit_execute(
    commit_record: dict[str, Any],
) -> dict[str, Any]:
    commit = _as_mapping(commit_record)
    return {
        "dispatch_commit_id": commit.get("dispatch_commit_id"),
        "dispatch_id": commit.get("dispatch_id"),
        "commit_status": commit.get("commit_status", "denied"),
        "can_execute": False,
        "blocked": True,
        "blocked_reason": "executor_dispatch_execution_boundary_not_open",
        "executor_run_allowed": False,
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


def build_runtime_task_dispatch_commit_audit_projection(
    commit_record: dict[str, Any] | None,
) -> dict[str, Any]:
    commit = _as_mapping(commit_record)
    return {
        "projection": "runtime_task_dispatch_commit_audit",
        "projection_only": True,
        "dispatch_commit_id": commit.get("dispatch_commit_id"),
        "dispatch_id": commit.get("dispatch_id"),
        "task_admission_id": commit.get("task_admission_id"),
        "executor_binding_id": commit.get("executor_binding_id"),
        "commit_status": commit.get("commit_status", "denied"),
        "denial_reason": commit.get("denial_reason", "not_evaluated"),
        "commit_time": commit.get("commit_time"),
        "executor_target": _as_mapping(commit.get("executor_target")),
        "committed_record_only": commit.get("commit_status") == "committed",
        "dispatch_ready": commit.get("commit_status") == "committed",
        "executor_run_performed": False,
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


def build_runtime_task_dispatch_commit_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_task_dispatch_commit_request(request)
    commit = build_runtime_task_dispatch_commit_record(request)
    return {
        "audit_schema": RUNTIME_TASK_DISPATCH_COMMIT_SCHEMA + ".audit",
        "decision": "reserved_runtime_task_dispatch_commit_record_only",
        "dispatch_commit_request_id": validation.get("dispatch_commit_request_id"),
        "dispatch_id": validation.get("dispatch_id"),
        "task_admission_id": validation.get("task_admission_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "request_valid": validation["valid"],
        "dispatch_commit_record": commit,
        "audit_projection": commit["audit_record"],
        "executor_run_performed": False,
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


def build_runtime_task_dispatch_commit_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_task_dispatch_commit_audit_record(request)
    commit = _as_mapping(audit.get("dispatch_commit_record"))
    return {
        "seal": "runtime_task_dispatch_commit_bundle",
        "schema": RUNTIME_TASK_DISPATCH_COMMIT_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_DISPATCH_COMMIT_RECORDS_ONLY_NO_EXECUTOR_EXECUTION",
        "dispatch_commit_id": commit.get("dispatch_commit_id"),
        "dispatch_id": commit.get("dispatch_id"),
        "task_admission_id": commit.get("task_admission_id"),
        "commit_status": commit.get("commit_status"),
        "audit_decision": audit["decision"],
        "executor_run_performed": False,
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
    "RUNTIME_TASK_DISPATCH_COMMIT_SCHEMA",
    "DISPATCH_COMMIT_STATUSES",
    "REQUIRED_DISPATCH_COMMIT_FIELDS",
    "DISPATCH_COMMIT_LOCKS",
    "build_runtime_task_dispatch_commit_request",
    "validate_runtime_task_dispatch_commit_request",
    "build_runtime_task_dispatch_commit_record",
    "expire_runtime_task_dispatch_commit",
    "revoke_runtime_task_dispatch_commit",
    "can_runtime_task_dispatch_commit_execute",
    "build_runtime_task_dispatch_commit_audit_projection",
    "build_runtime_task_dispatch_commit_audit_record",
    "build_runtime_task_dispatch_commit_milestone_seal",
]
