from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_LOOP_RESUME_POLICY_SCHEMA = "zero.runtime.loop_resume_policy.v1"

RUNTIME_RESUME_ACTIONS = (
    "CONTINUE_EXECUTION",
    "WAIT_FOR_INPUT",
    "ENTER_RECOVERY",
    "MARK_COMPLETE",
    "BLOCKED",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _decision_id(
    *,
    runtime_id: str | None,
    progress_snapshot_id: str | None,
    cursor_id: str | None,
    action: str,
    next_step: Any,
    recovery_required: bool,
    reason: str,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "progress_snapshot_id": progress_snapshot_id,
            "cursor_id": cursor_id,
            "action": action,
            "next_step": next_step,
            "recovery_required": recovery_required,
            "reason": reason,
        }
    )
    return f"runtime-loop-resume-decision::{runtime_id or 'missing-runtime'}::{fragment}"


def _next_step(cursor: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "next_step_index": cursor.get("next_step_index"),
        "last_committed_step": _as_mapping(
            cursor.get("last_committed_step") or snapshot.get("last_committed_step")
        ),
    }


def _decide_action(
    snapshot: dict[str, Any],
    cursor: dict[str, Any],
) -> tuple[str, bool, str]:
    state = cursor.get("state")
    recovery_required = (
        cursor.get("recovery_required") is True
        or snapshot.get("recovery_required") is True
    )

    if state == "COMPLETE":
        return "MARK_COMPLETE", False, "resume_cursor_complete"
    if state == "BLOCKED":
        return "BLOCKED", recovery_required, "resume_cursor_blocked"
    if recovery_required or state == "RECOVERY_REQUIRED":
        return "ENTER_RECOVERY", True, "recovery_required_by_progress_or_cursor"
    if state == "WAITING":
        return "WAIT_FOR_INPUT", False, "resume_cursor_waiting_for_input"
    if state == "CONTINUE":
        return "CONTINUE_EXECUTION", False, "resume_cursor_continue"
    return "WAIT_FOR_INPUT", recovery_required, "resume_cursor_state_unknown"


def build_runtime_resume_decision(
    progress_snapshot: dict[str, Any] | None,
    resume_cursor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = _as_mapping(progress_snapshot)
    cursor = _as_mapping(resume_cursor or snapshot.get("resume_cursor"))
    action, recovery_required, reason = _decide_action(snapshot, cursor)
    next_step = _next_step(cursor, snapshot)
    runtime_id = cursor.get("runtime_id") or snapshot.get("runtime_id")
    decision_id = _decision_id(
        runtime_id=runtime_id,
        progress_snapshot_id=snapshot.get("progress_snapshot_id"),
        cursor_id=cursor.get("cursor_id"),
        action=action,
        next_step=next_step,
        recovery_required=recovery_required,
        reason=reason,
    )

    return {
        "schema": RUNTIME_LOOP_RESUME_POLICY_SCHEMA,
        "decision_id": decision_id,
        "runtime_id": runtime_id,
        "progress_snapshot_id": snapshot.get("progress_snapshot_id"),
        "cursor_id": cursor.get("cursor_id"),
        "action": action,
        "next_step": next_step,
        "recovery_required": recovery_required,
        "reason": reason,
        "record_only": True,
        "decision_only": True,
        "task_execution_performed": False,
        "executor_run_performed": False,
        "scheduler_mutation_performed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
        "automatic_retry_performed": False,
        "progress_memory_mutated": False,
    }


def build_runtime_loop_resume_policy_audit_projection(
    resume_decision: dict[str, Any] | None,
) -> dict[str, Any]:
    decision = _as_mapping(resume_decision)
    return {
        "projection": "runtime_loop_resume_policy_audit",
        "projection_only": True,
        "decision_id": decision.get("decision_id"),
        "runtime_id": decision.get("runtime_id"),
        "progress_snapshot_id": decision.get("progress_snapshot_id"),
        "cursor_id": decision.get("cursor_id"),
        "action": decision.get("action"),
        "next_step": _as_mapping(decision.get("next_step")),
        "recovery_required": decision.get("recovery_required") is True,
        "reason": decision.get("reason", "not_evaluated"),
        "task_execution_performed": False,
        "executor_run_performed": False,
        "scheduler_mutation_performed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
        "automatic_retry_performed": False,
        "progress_memory_mutated": False,
    }


def build_runtime_loop_resume_policy_audit_record(
    progress_snapshot: dict[str, Any] | None,
    resume_cursor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision = build_runtime_resume_decision(progress_snapshot, resume_cursor)
    return {
        "audit_schema": RUNTIME_LOOP_RESUME_POLICY_SCHEMA + ".audit",
        "decision": "reserved_runtime_loop_resume_policy_decision_only",
        "resume_decision": decision,
        "audit_projection": build_runtime_loop_resume_policy_audit_projection(decision),
        "task_execution_performed": False,
        "executor_run_performed": False,
        "scheduler_mutation_performed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
        "automatic_retry_performed": False,
        "progress_memory_mutated": False,
    }


def build_runtime_loop_resume_policy_milestone_seal(
    progress_snapshot: dict[str, Any] | None,
    resume_cursor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = build_runtime_loop_resume_policy_audit_record(
        progress_snapshot, resume_cursor
    )
    decision = _as_mapping(audit.get("resume_decision"))
    return {
        "seal": "runtime_loop_resume_policy_bundle",
        "schema": RUNTIME_LOOP_RESUME_POLICY_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_LOOP_RESUME_POLICY_DECISIONS_ONLY",
        "decision_id": decision.get("decision_id"),
        "action": decision.get("action"),
        "recovery_required": decision.get("recovery_required") is True,
        "decision_only": True,
        "task_execution_performed": False,
        "executor_run_performed": False,
        "scheduler_mutation_performed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
        "automatic_retry_performed": False,
        "progress_memory_mutated": False,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "RUNTIME_LOOP_RESUME_POLICY_SCHEMA",
    "RUNTIME_RESUME_ACTIONS",
    "build_runtime_resume_decision",
    "build_runtime_loop_resume_policy_audit_projection",
    "build_runtime_loop_resume_policy_audit_record",
    "build_runtime_loop_resume_policy_milestone_seal",
]
