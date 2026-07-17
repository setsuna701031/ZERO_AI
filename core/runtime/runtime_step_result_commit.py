from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_STEP_RESULT_COMMIT_SCHEMA = "zero.runtime.step_result_commit.v1"

STEP_RESULT_STATUSES = (
    "committed",
    "denied",
    "failed",
    "blocked",
    "recovery_required",
)

STEP_RESULT_KINDS = (
    "noop",
    "read_result",
    "write_result",
    "mutation_result",
    "recovery_result",
    "failure_result",
)

REQUIRED_STEP_RESULT_COMMIT_FIELDS = (
    "step_result_commit_request_id",
    "runtime_session_id",
    "execution_lease_id",
    "capability_grant_id",
    "executor_binding_id",
    "work_cycle_id",
    "execution_tick_id",
    "step_bridge",
    "result_kind",
    "result_summary",
    "progress_delta",
    "audit_required",
)

STEP_RESULT_COMMIT_LOCKS = {
    "record_only": True,
    "result_evidence_only": True,
    "executor_run_allowed": False,
    "step_execution_allowed": False,
    "task_execution_allowed": False,
    "tool_invocation_allowed": False,
    "subprocess_allowed": False,
    "shell_allowed": False,
    "network_allowed": False,
    "filesystem_read_allowed": False,
    "filesystem_write_allowed": False,
    "filesystem_mutation_allowed": False,
    "state_mutation_allowed": False,
    "task_completion_allowed": False,
    "autonomy_loop_allowed": False,
    "self_start_allowed": False,
    "background_worker_allowed": False,
}


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_STEP_RESULT_COMMIT_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in STEP_RESULT_COMMIT_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _step_result_commit_id(
    *,
    request_id: str,
    runtime_session_id: str,
    step_bridge_id: str,
    step_request_id: str,
    work_cycle_id: str,
    execution_tick_id: str,
    result_kind: str,
) -> str:
    fragment = _stable_fragment(
        {
            "request_id": request_id,
            "runtime_session_id": runtime_session_id,
            "step_bridge_id": step_bridge_id,
            "step_request_id": step_request_id,
            "work_cycle_id": work_cycle_id,
            "execution_tick_id": execution_tick_id,
            "result_kind": result_kind,
        }
    )
    return (
        f"runtime-step-result-commit::{runtime_session_id}::"
        f"{step_request_id}::{fragment}"
    )


def build_runtime_step_result_commit_request(
    *,
    step_result_commit_request_id: str,
    runtime_session_id: str | None = None,
    execution_lease_id: str | None = None,
    capability_grant_id: str | None = None,
    executor_binding_id: str | None = None,
    work_cycle_id: str | None = None,
    execution_tick_id: str | None = None,
    step_bridge: dict[str, Any] | None = None,
    result_kind: str = "noop",
    result_summary: str = "caller_supplied_noop_result_evidence",
    failure_reason: str = "none",
    progress_delta: dict[str, Any] | None = None,
    recovery_required: bool = False,
    task_completion_candidate: bool = False,
    commit_reason: str = "explicit_runtime_step_result_commit",
    commit_time: str = "deterministic-time::1377",
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_STEP_RESULT_COMMIT_SCHEMA,
        "step_result_commit_request_id": step_result_commit_request_id,
        "runtime_session_id": runtime_session_id,
        "execution_lease_id": execution_lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "work_cycle_id": work_cycle_id,
        "execution_tick_id": execution_tick_id,
        "step_bridge": _as_mapping(step_bridge),
        "result_kind": result_kind,
        "result_summary": result_summary,
        "failure_reason": failure_reason,
        "progress_delta": _as_mapping(progress_delta),
        "recovery_required": recovery_required,
        "task_completion_candidate": task_completion_candidate,
        "commit_reason": commit_reason,
        "commit_time": commit_time,
        "boundary_locks": deepcopy(STEP_RESULT_COMMIT_LOCKS),
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


def _evaluate_runtime_step_result_commit_request(
    record: dict[str, Any],
) -> dict[str, Any]:
    bridge = _as_mapping(record.get("step_bridge"))

    runtime_session_id = record.get("runtime_session_id")
    execution_lease_id = record.get("execution_lease_id")
    capability_grant_id = record.get("capability_grant_id")
    executor_binding_id = record.get("executor_binding_id")
    work_cycle_id = record.get("work_cycle_id")
    execution_tick_id = record.get("execution_tick_id")
    step_bridge_id = bridge.get("step_bridge_id")
    step_request_id = bridge.get("step_request_id")
    bridge_status = bridge.get("bridge_status")
    result_kind = record.get("result_kind")
    recovery_required = (
        record.get("recovery_required") is True or result_kind == "recovery_result"
    )
    failure_reason = record.get("failure_reason", "none")

    problems: list[str] = []
    if not step_bridge_id:
        problems.append("missing_step_bridge")
    if not step_request_id:
        problems.append("missing_step_request_id")
    if not runtime_session_id:
        problems.append("missing_runtime_session_id")
    if not execution_lease_id:
        problems.append("missing_execution_lease_id")
    if not capability_grant_id:
        problems.append("missing_capability_grant_id")
    if not executor_binding_id:
        problems.append("missing_executor_binding_id")
    if not work_cycle_id:
        problems.append("missing_work_cycle_id")
    if not execution_tick_id:
        problems.append("missing_execution_tick_id")
    if result_kind not in STEP_RESULT_KINDS:
        problems.append("unsupported_result_kind")
    if result_kind == "failure_result" and not failure_reason:
        problems.append("missing_failure_reason")

    for field, expected in (
        ("runtime_session_id", runtime_session_id),
        ("execution_lease_id", execution_lease_id),
        ("capability_grant_id", capability_grant_id),
        ("executor_binding_id", executor_binding_id),
        ("work_cycle_id", work_cycle_id),
        ("execution_tick_id", execution_tick_id),
    ):
        if field in bridge and bridge.get(field) != expected:
            problems.append(f"step_bridge_{field}_mismatch")

    if bridge_status == "denied":
        problems.append("denied_step_bridge")
    elif bridge_status == "blocked":
        problems.append("blocked_step_bridge")
    elif bridge_status in {"expired", "revoked"}:
        problems.append(f"{bridge_status}_step_bridge")
    elif step_bridge_id and bridge_status != "bridged":
        problems.append("step_bridge_not_bridged")

    if bridge.get("record_only") is not True and step_bridge_id:
        problems.append("step_bridge_not_record_only")
    if bridge.get("step_executed") is not False and step_bridge_id:
        problems.append("step_bridge_step_execution_detected")
    if bridge.get("task_execution_performed") is not False and step_bridge_id:
        problems.append("step_bridge_task_execution_detected")
    if bridge.get("tool_invoked") is not False and step_bridge_id:
        problems.append("step_bridge_tool_invocation_detected")
    if bridge.get("filesystem_mutation_performed") is not False and step_bridge_id:
        problems.append("step_bridge_filesystem_mutation_detected")
    if bridge.get("task_completed") is not False and step_bridge_id:
        problems.append("step_bridge_task_completion_detected")

    return {
        "runtime_session_id": runtime_session_id,
        "execution_lease_id": execution_lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "work_cycle_id": work_cycle_id,
        "execution_tick_id": execution_tick_id,
        "step_bridge_id": step_bridge_id,
        "step_request_id": step_request_id,
        "bridge_status": bridge_status,
        "result_kind": result_kind,
        "result_summary": record.get("result_summary"),
        "failure_reason": failure_reason,
        "progress_delta": _as_mapping(record.get("progress_delta")),
        "recovery_required": recovery_required,
        "task_completion_candidate": record.get("task_completion_candidate") is True,
        "problems": list(dict.fromkeys(problems)),
    }


def validate_runtime_step_result_commit_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_runtime_step_result_commit_request(record)
    problems = list(evaluation["problems"])
    if missing:
        problems.append("missing_required_fields")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")
    problems = list(dict.fromkeys(problems))

    if evaluation["bridge_status"] == "denied" or "boundary_unlock_attempt" in problems:
        status = "denied"
    elif problems:
        status = "blocked"
    elif evaluation["recovery_required"]:
        status = "recovery_required"
    elif evaluation["result_kind"] == "failure_result":
        status = "failed"
    else:
        status = "committed"

    return {
        "schema": RUNTIME_STEP_RESULT_COMMIT_SCHEMA,
        "valid": not problems and status in {"committed", "failed", "recovery_required"},
        "step_result_commit_request_id": record.get("step_result_commit_request_id"),
        "result_status": status,
        "denial_reason": "none" if not problems else ";".join(problems),
        "problems": problems,
        "missing_required_fields": missing,
        "unlock_attempts": unlocks,
        "step_executed": False,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_read_performed": False,
        "filesystem_write_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "task_marked_complete": False,
        "autonomy_loop_started": False,
        "self_start_performed": False,
        "background_worker_started": False,
        **evaluation,
    }


def build_runtime_step_result_commit_record(request: dict[str, Any]) -> dict[str, Any]:
    validation = validate_runtime_step_result_commit_request(request)
    record = _as_mapping(request)
    commit_id = _step_result_commit_id(
        request_id=str(validation.get("step_result_commit_request_id") or "missing-request"),
        runtime_session_id=str(validation.get("runtime_session_id") or "missing-session"),
        step_bridge_id=str(validation.get("step_bridge_id") or "missing-bridge"),
        step_request_id=str(validation.get("step_request_id") or "missing-step-request"),
        work_cycle_id=str(validation.get("work_cycle_id") or "missing-cycle"),
        execution_tick_id=str(validation.get("execution_tick_id") or "missing-tick"),
        result_kind=str(validation.get("result_kind") or "missing-result-kind"),
    )
    commit = {
        "schema": RUNTIME_STEP_RESULT_COMMIT_SCHEMA,
        "step_result_commit_id": commit_id,
        "step_result_commit_request_id": validation.get(
            "step_result_commit_request_id"
        ),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "step_bridge_id": validation.get("step_bridge_id"),
        "step_request_id": validation.get("step_request_id"),
        "work_cycle_id": validation.get("work_cycle_id"),
        "execution_tick_id": validation.get("execution_tick_id"),
        "result_status": validation["result_status"],
        "result_kind": validation.get("result_kind"),
        "result_summary": validation.get("result_summary"),
        "failure_reason": validation.get("failure_reason"),
        "progress_delta": validation.get("progress_delta"),
        "recovery_required": validation["recovery_required"],
        "task_completion_candidate": validation["task_completion_candidate"],
        "denial_reason": validation["denial_reason"],
        "commit_reason": record.get("commit_reason"),
        "commit_time": record.get("commit_time"),
        "supported_statuses": list(STEP_RESULT_STATUSES),
        "supported_result_kinds": list(STEP_RESULT_KINDS),
        "record_only": True,
        "result_evidence_only": True,
        "step_executed": False,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_read_performed": False,
        "filesystem_write_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "task_marked_complete": False,
        "autonomy_loop_started": False,
        "self_start_performed": False,
        "background_worker_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }
    commit["audit_projection"] = build_runtime_step_result_commit_audit_projection(
        commit
    )
    return commit


def build_runtime_step_result_commit_audit_projection(
    commit_record: dict[str, Any] | None,
) -> dict[str, Any]:
    commit = _as_mapping(commit_record)
    return {
        "projection": "runtime_step_result_commit_audit",
        "projection_only": True,
        "step_result_commit_id": commit.get("step_result_commit_id"),
        "runtime_session_id": commit.get("runtime_session_id"),
        "step_bridge_id": commit.get("step_bridge_id"),
        "step_request_id": commit.get("step_request_id"),
        "work_cycle_id": commit.get("work_cycle_id"),
        "execution_tick_id": commit.get("execution_tick_id"),
        "result_status": commit.get("result_status", "denied"),
        "result_kind": commit.get("result_kind"),
        "result_summary": commit.get("result_summary"),
        "failure_reason": commit.get("failure_reason", "none"),
        "progress_delta": _as_mapping(commit.get("progress_delta")),
        "recovery_required": commit.get("recovery_required") is True,
        "task_completion_candidate": commit.get("task_completion_candidate") is True,
        "committed_evidence_only": commit.get("result_status")
        in {"committed", "failed", "recovery_required"},
        "record_only": True,
        "step_executed": False,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "filesystem_read_performed": False,
        "filesystem_write_performed": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "task_marked_complete": False,
        "autonomy_loop_started": False,
        "self_start_performed": False,
        "background_worker_started": False,
    }


def can_runtime_step_result_commit_complete_task(
    commit_record: dict[str, Any],
) -> dict[str, Any]:
    commit = _as_mapping(commit_record)
    return {
        "step_result_commit_id": commit.get("step_result_commit_id"),
        "result_status": commit.get("result_status", "denied"),
        "task_completion_candidate": commit.get("task_completion_candidate") is True,
        "can_complete_task": False,
        "can_mark_task_complete": False,
        "can_execute_step": False,
        "can_run_executor": False,
        "can_invoke_tools": False,
        "can_mutate_filesystem": False,
        "can_start_background_loop": False,
        "blocked_reason": "runtime_step_result_commit_completion_disabled",
    }


def build_runtime_step_result_commit_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_step_result_commit_request(request)
    commit = build_runtime_step_result_commit_record(request)
    return {
        "audit_schema": RUNTIME_STEP_RESULT_COMMIT_SCHEMA + ".audit",
        "decision": "reserved_runtime_step_result_commit_record_only",
        "step_result_commit_request_id": validation.get(
            "step_result_commit_request_id"
        ),
        "runtime_session_id": validation.get("runtime_session_id"),
        "step_bridge_id": validation.get("step_bridge_id"),
        "step_request_id": validation.get("step_request_id"),
        "work_cycle_id": validation.get("work_cycle_id"),
        "execution_tick_id": validation.get("execution_tick_id"),
        "request_valid": validation["valid"],
        "runtime_step_result_commit_record": commit,
        "audit_projection": commit["audit_projection"],
        "step_executed": False,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "filesystem_mutation_performed": False,
        "task_completed": False,
        "task_marked_complete": False,
        "autonomy_loop_started": False,
        "self_start_performed": False,
        "background_worker_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
        "non_mainline_issues": validation["problems"],
    }


def build_runtime_step_result_commit_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_step_result_commit_audit_record(request)
    commit = _as_mapping(audit.get("runtime_step_result_commit_record"))
    return {
        "seal": "runtime_step_result_commit_bundle",
        "schema": RUNTIME_STEP_RESULT_COMMIT_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_STEP_RESULT_COMMIT_RECORDS_ONLY",
        "step_result_commit_id": commit.get("step_result_commit_id"),
        "step_bridge_id": commit.get("step_bridge_id"),
        "step_request_id": commit.get("step_request_id"),
        "work_cycle_id": commit.get("work_cycle_id"),
        "execution_tick_id": commit.get("execution_tick_id"),
        "result_status": commit.get("result_status"),
        "audit_decision": audit["decision"],
        "result_evidence_only": True,
        "step_executed": False,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "filesystem_mutation_performed": False,
        "task_completed": False,
        "task_marked_complete": False,
        "autonomy_loop_started": False,
        "self_start_performed": False,
        "background_worker_started": False,
        "forbidden_surfaces_locked": True,
        "audit_required": True,
    }


__all__ = [
    "RUNTIME_STEP_RESULT_COMMIT_SCHEMA",
    "STEP_RESULT_STATUSES",
    "STEP_RESULT_KINDS",
    "REQUIRED_STEP_RESULT_COMMIT_FIELDS",
    "STEP_RESULT_COMMIT_LOCKS",
    "build_runtime_step_result_commit_request",
    "validate_runtime_step_result_commit_request",
    "build_runtime_step_result_commit_record",
    "build_runtime_step_result_commit_audit_projection",
    "can_runtime_step_result_commit_complete_task",
    "build_runtime_step_result_commit_audit_record",
    "build_runtime_step_result_commit_milestone_seal",
]
