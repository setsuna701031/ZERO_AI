from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_TASK_DISPATCH_PREPARATION_SCHEMA = (
    "zero.runtime.task_dispatch_preparation.v1"
)

DISPATCH_PREPARATION_STATUSES = ("prepared", "denied", "expired", "revoked")

REQUIRED_DISPATCH_PREPARATION_FIELDS = (
    "dispatch_preparation_request_id",
    "task_admission",
    "runtime_session_id",
    "execution_lease",
    "capability_grant",
    "executor_binding",
    "audit_required",
)

DISPATCH_PREPARATION_LOCKS = {
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
    return [field for field in REQUIRED_DISPATCH_PREPARATION_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in DISPATCH_PREPARATION_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _dispatch_id(
    *,
    request_id: str,
    task_admission_id: str,
    executor_binding_id: str,
    runtime_session_id: str,
) -> str:
    fragment = _stable_fragment(
        {
            "request_id": request_id,
            "task_admission_id": task_admission_id,
            "executor_binding_id": executor_binding_id,
            "runtime_session_id": runtime_session_id,
        }
    )
    return f"task-dispatch::{runtime_session_id}::{task_admission_id}::{fragment}"


def build_runtime_task_dispatch_preparation_request(
    *,
    dispatch_preparation_request_id: str,
    task_admission: dict[str, Any] | None = None,
    runtime_session_id: str | None = None,
    execution_lease: dict[str, Any] | None = None,
    capability_grant: dict[str, Any] | None = None,
    executor_binding: dict[str, Any] | None = None,
    preparation_time: str = "deterministic-time::1321",
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_TASK_DISPATCH_PREPARATION_SCHEMA,
        "dispatch_preparation_request_id": dispatch_preparation_request_id,
        "task_admission": _as_mapping(task_admission),
        "runtime_session_id": runtime_session_id,
        "execution_lease": _as_mapping(execution_lease),
        "capability_grant": _as_mapping(capability_grant),
        "executor_binding": _as_mapping(executor_binding),
        "preparation_time": preparation_time,
        "boundary_locks": deepcopy(DISPATCH_PREPARATION_LOCKS),
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


def _evaluate_dispatch_preparation_request(record: dict[str, Any]) -> dict[str, Any]:
    admission = _as_mapping(record.get("task_admission"))
    lease = _as_mapping(record.get("execution_lease"))
    grant = _as_mapping(record.get("capability_grant"))
    binding = _as_mapping(record.get("executor_binding"))

    runtime_session_id = record.get("runtime_session_id")
    task_admission_id = admission.get("task_admission_id")
    execution_lease_id = lease.get("lease_id") or admission.get("execution_lease_id")
    capability_grant_id = grant.get("capability_grant_id") or admission.get(
        "capability_grant_id"
    )
    executor_binding_id = binding.get("executor_binding_id") or admission.get(
        "executor_binding_id"
    )
    requested_task_id = admission.get("requested_task_id")
    requested_task_type = admission.get("requested_task_type")

    admitted = (
        bool(task_admission_id)
        and admission.get("runtime_session_id") == runtime_session_id
        and admission.get("admission_status") == "admitted"
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

    problems: list[str] = []
    if not task_admission_id:
        problems.append("missing_task_admission")
    elif not admitted:
        problems.append("task_admission_not_admitted")
    if admission.get("admission_status") == "denied":
        problems.append("denied_admission")
    if admission.get("admission_status") == "expired":
        problems.append("expired_admission")
    if admission.get("admission_status") == "revoked":
        problems.append("revoked_admission")
    if not runtime_session_id:
        problems.append("invalid_runtime_session_id")
    if admission and admission.get("execution_lease_id") != execution_lease_id:
        problems.append("task_admission_lease_mismatch")
    if admission and admission.get("capability_grant_id") != capability_grant_id:
        problems.append("task_admission_capability_mismatch")
    if admission and admission.get("executor_binding_id") != executor_binding_id:
        problems.append("task_admission_executor_binding_mismatch")
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
        "task_admission_id": task_admission_id,
        "runtime_session_id": runtime_session_id,
        "execution_lease_id": execution_lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "requested_task_id": requested_task_id,
        "requested_task_type": requested_task_type,
        "problems": problems,
    }


def validate_runtime_task_dispatch_preparation_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_dispatch_preparation_request(record)
    problems = list(dict.fromkeys(evaluation["problems"]))
    if missing:
        problems.append("missing_required_fields")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")

    status = "prepared" if not problems else "denied"
    return {
        "schema": RUNTIME_TASK_DISPATCH_PREPARATION_SCHEMA,
        "valid": not problems,
        "dispatch_preparation_request_id": record.get(
            "dispatch_preparation_request_id"
        ),
        "task_admission_id": evaluation["task_admission_id"],
        "runtime_session_id": evaluation["runtime_session_id"],
        "execution_lease_id": evaluation["execution_lease_id"],
        "capability_grant_id": evaluation["capability_grant_id"],
        "executor_binding_id": evaluation["executor_binding_id"],
        "requested_task_id": evaluation["requested_task_id"],
        "requested_task_type": evaluation["requested_task_type"],
        "dispatch_status": status,
        "preparation_allowed": not problems,
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


def build_runtime_task_dispatch_preparation_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_task_dispatch_preparation_request(request)
    record = _as_mapping(request)
    binding = _as_mapping(record.get("executor_binding"))
    dispatch_id = _dispatch_id(
        request_id=str(validation.get("dispatch_preparation_request_id")),
        task_admission_id=str(validation.get("task_admission_id")),
        executor_binding_id=str(validation.get("executor_binding_id")),
        runtime_session_id=str(validation.get("runtime_session_id")),
    )
    dispatch_plan = {
        "plan_type": "dispatch_preparation_record_only",
        "requested_task_id": validation.get("requested_task_id"),
        "requested_task_type": validation.get("requested_task_type"),
        "task_admission_id": validation.get("task_admission_id"),
        "executor_run_allowed": False,
        "tool_invocation_allowed": False,
        "state_mutation_allowed": False,
    }
    executor_target = {
        "executor_binding_id": validation.get("executor_binding_id"),
        "executor_id": binding.get("executor_id", "executor-zero"),
        "executor_type": binding.get("executor_type", "runtime_task_executor"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "target_mode": "record_only",
    }
    dispatch = {
        "dispatch_id": dispatch_id,
        "task_admission_id": validation.get("task_admission_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "dispatch_status": validation["dispatch_status"],
        "dispatch_plan": dispatch_plan,
        "executor_target": executor_target,
        "preparation_time": record.get("preparation_time"),
        "denial_reason": validation["denial_reason"],
        "audit_record": {},
        "supported_statuses": list(DISPATCH_PREPARATION_STATUSES),
        "record_only": True,
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
    dispatch["audit_record"] = build_runtime_task_dispatch_preparation_audit_projection(
        dispatch
    )
    return dispatch


def expire_runtime_task_dispatch_preparation(
    dispatch_record: dict[str, Any],
    *,
    reason: str = "dispatch_preparation_expired",
) -> dict[str, Any]:
    dispatch = _as_mapping(dispatch_record)
    dispatch["dispatch_status"] = "expired"
    dispatch["denial_reason"] = reason
    dispatch["executor_run_performed"] = False
    dispatch["audit_record"] = build_runtime_task_dispatch_preparation_audit_projection(
        dispatch
    )
    return dispatch


def revoke_runtime_task_dispatch_preparation(
    dispatch_record: dict[str, Any],
    *,
    reason: str = "dispatch_preparation_revoked",
) -> dict[str, Any]:
    dispatch = _as_mapping(dispatch_record)
    dispatch["dispatch_status"] = "revoked"
    dispatch["denial_reason"] = reason
    dispatch["executor_run_performed"] = False
    dispatch["audit_record"] = build_runtime_task_dispatch_preparation_audit_projection(
        dispatch
    )
    return dispatch


def can_runtime_dispatch_execute(dispatch_record: dict[str, Any]) -> dict[str, Any]:
    dispatch = _as_mapping(dispatch_record)
    return {
        "dispatch_id": dispatch.get("dispatch_id"),
        "dispatch_status": dispatch.get("dispatch_status", "denied"),
        "can_execute": False,
        "blocked": True,
        "blocked_reason": "executor_dispatch_execution_disabled",
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


def build_runtime_task_dispatch_preparation_audit_projection(
    dispatch_record: dict[str, Any] | None,
) -> dict[str, Any]:
    dispatch = _as_mapping(dispatch_record)
    return {
        "projection": "runtime_task_dispatch_preparation_audit",
        "projection_only": True,
        "dispatch_id": dispatch.get("dispatch_id"),
        "task_admission_id": dispatch.get("task_admission_id"),
        "executor_binding_id": dispatch.get("executor_binding_id"),
        "dispatch_status": dispatch.get("dispatch_status", "denied"),
        "denial_reason": dispatch.get("denial_reason", "not_evaluated"),
        "preparation_time": dispatch.get("preparation_time"),
        "executor_target": _as_mapping(dispatch.get("executor_target")),
        "prepared_record_only": dispatch.get("dispatch_status") == "prepared",
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


def build_runtime_task_dispatch_preparation_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_task_dispatch_preparation_request(request)
    dispatch = build_runtime_task_dispatch_preparation_record(request)
    return {
        "audit_schema": RUNTIME_TASK_DISPATCH_PREPARATION_SCHEMA + ".audit",
        "decision": "reserved_runtime_task_dispatch_preparation_record_only",
        "dispatch_preparation_request_id": validation.get(
            "dispatch_preparation_request_id"
        ),
        "task_admission_id": validation.get("task_admission_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "request_valid": validation["valid"],
        "dispatch_preparation_record": dispatch,
        "audit_projection": dispatch["audit_record"],
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


def build_runtime_task_dispatch_preparation_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_task_dispatch_preparation_audit_record(request)
    dispatch = _as_mapping(audit.get("dispatch_preparation_record"))
    return {
        "seal": "runtime_task_dispatch_preparation_bundle",
        "schema": RUNTIME_TASK_DISPATCH_PREPARATION_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_DISPATCH_PREPARATION_RECORDS_ONLY_NO_EXECUTOR_EXECUTION",
        "dispatch_id": dispatch.get("dispatch_id"),
        "task_admission_id": dispatch.get("task_admission_id"),
        "dispatch_status": dispatch.get("dispatch_status"),
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
    "RUNTIME_TASK_DISPATCH_PREPARATION_SCHEMA",
    "DISPATCH_PREPARATION_STATUSES",
    "REQUIRED_DISPATCH_PREPARATION_FIELDS",
    "DISPATCH_PREPARATION_LOCKS",
    "build_runtime_task_dispatch_preparation_request",
    "validate_runtime_task_dispatch_preparation_request",
    "build_runtime_task_dispatch_preparation_record",
    "expire_runtime_task_dispatch_preparation",
    "revoke_runtime_task_dispatch_preparation",
    "can_runtime_dispatch_execute",
    "build_runtime_task_dispatch_preparation_audit_projection",
    "build_runtime_task_dispatch_preparation_audit_record",
    "build_runtime_task_dispatch_preparation_milestone_seal",
]
