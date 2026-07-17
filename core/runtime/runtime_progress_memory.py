from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

from core.runtime.runtime_resume_cursor import build_runtime_resume_cursor


RUNTIME_PROGRESS_MEMORY_SCHEMA = "zero.runtime.progress_memory.v1"

PROGRESS_COMMIT_STATUSES = ("committed", "failed", "recovery_required")


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return deepcopy(value) if isinstance(value, list) else []


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _step_projection(commit: dict[str, Any]) -> dict[str, Any]:
    delta = _as_mapping(commit.get("progress_delta"))
    return {
        "step_result_commit_id": commit.get("step_result_commit_id"),
        "step_request_id": commit.get("step_request_id"),
        "step_bridge_id": commit.get("step_bridge_id"),
        "work_cycle_id": commit.get("work_cycle_id"),
        "execution_tick_id": commit.get("execution_tick_id"),
        "result_status": commit.get("result_status"),
        "result_kind": commit.get("result_kind"),
        "step_id": delta.get("step_id") or commit.get("step_request_id"),
        "step_index": delta.get("step_index"),
        "next_step_index": delta.get("next_step_index"),
        "result_summary": commit.get("result_summary"),
        "failure_reason": commit.get("failure_reason", "none"),
    }


def _dedupe_commits(commit_history: list[Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in commit_history:
        commit = _as_mapping(item)
        commit_id = commit.get("step_result_commit_id")
        if not commit_id or commit_id in seen:
            continue
        seen.add(commit_id)
        deduped.append(commit)
    return deduped


def build_runtime_progress_snapshot(
    commit_history: list[Any] | None,
    *,
    runtime_id: str | None = None,
    total_steps: int | None = None,
) -> dict[str, Any]:
    commits = _dedupe_commits(_as_list(commit_history))
    inferred_runtime_id = runtime_id
    if inferred_runtime_id is None and commits:
        inferred_runtime_id = commits[0].get("runtime_session_id")

    completed_steps: list[dict[str, Any]] = []
    failed_steps: list[dict[str, Any]] = []
    skipped_steps: list[dict[str, Any]] = []
    last_committed_step: dict[str, Any] = {}
    recovery_required = False

    for commit in commits:
        if commit.get("record_only") is not True:
            continue
        if commit.get("result_status") not in PROGRESS_COMMIT_STATUSES:
            continue
        projection = _step_projection(commit)
        last_committed_step = projection
        if commit.get("recovery_required") is True or commit.get("result_status") == "recovery_required":
            recovery_required = True
        if commit.get("result_status") == "failed" or commit.get("result_kind") == "failure_result":
            recovery_required = True
            failed_steps.append(projection)
        elif commit.get("result_status") == "recovery_required":
            failed_steps.append(projection)
        elif commit.get("result_kind") == "noop":
            skipped_steps.append(projection)
        else:
            completed_steps.append(projection)

    snapshot_id = "runtime-progress-snapshot::" + str(inferred_runtime_id or "missing-runtime") + "::" + _stable_fragment(
        {
            "runtime_id": inferred_runtime_id,
            "commit_ids": tuple(commit.get("step_result_commit_id") for commit in commits),
            "completed": tuple(step.get("step_result_commit_id") for step in completed_steps),
            "failed": tuple(step.get("step_result_commit_id") for step in failed_steps),
            "skipped": tuple(step.get("step_result_commit_id") for step in skipped_steps),
            "recovery_required": recovery_required,
        }
    )

    snapshot = {
        "schema": RUNTIME_PROGRESS_MEMORY_SCHEMA,
        "progress_snapshot_id": snapshot_id,
        "runtime_id": inferred_runtime_id,
        "completed_steps": completed_steps,
        "failed_steps": failed_steps,
        "skipped_steps": skipped_steps,
        "last_committed_step": last_committed_step,
        "resume_cursor": {},
        "recovery_required": recovery_required,
        "commit_count": len(commits),
        "record_only": True,
        "projection_only": True,
        "task_execution_performed": False,
        "executor_run_performed": False,
        "scheduler_mutation_performed": False,
        "autonomy_loop_started": False,
        "repair_started": False,
    }
    snapshot["resume_cursor"] = build_runtime_resume_cursor(
        snapshot, total_steps=total_steps
    )
    snapshot["audit_projection"] = build_runtime_progress_memory_audit_projection(
        snapshot
    )
    return snapshot


def build_runtime_progress_memory_audit_projection(
    progress_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    snapshot = _as_mapping(progress_snapshot)
    return {
        "projection": "runtime_progress_memory_audit",
        "projection_only": True,
        "progress_snapshot_id": snapshot.get("progress_snapshot_id"),
        "runtime_id": snapshot.get("runtime_id"),
        "completed_count": len(snapshot.get("completed_steps", []))
        if isinstance(snapshot.get("completed_steps"), list)
        else 0,
        "failed_count": len(snapshot.get("failed_steps", []))
        if isinstance(snapshot.get("failed_steps"), list)
        else 0,
        "skipped_count": len(snapshot.get("skipped_steps", []))
        if isinstance(snapshot.get("skipped_steps"), list)
        else 0,
        "last_committed_step": _as_mapping(snapshot.get("last_committed_step")),
        "resume_cursor": _as_mapping(snapshot.get("resume_cursor")),
        "recovery_required": snapshot.get("recovery_required") is True,
        "commit_history_only": True,
        "task_execution_performed": False,
        "executor_run_performed": False,
        "scheduler_mutation_performed": False,
        "autonomy_loop_started": False,
        "repair_started": False,
    }


def build_runtime_progress_memory_audit_record(
    commit_history: list[Any] | None,
    *,
    runtime_id: str | None = None,
    total_steps: int | None = None,
) -> dict[str, Any]:
    snapshot = build_runtime_progress_snapshot(
        commit_history, runtime_id=runtime_id, total_steps=total_steps
    )
    return {
        "audit_schema": RUNTIME_PROGRESS_MEMORY_SCHEMA + ".audit",
        "decision": "reserved_runtime_progress_memory_projection_only",
        "runtime_id": snapshot.get("runtime_id"),
        "progress_snapshot": snapshot,
        "audit_projection": snapshot["audit_projection"],
        "task_execution_performed": False,
        "executor_run_performed": False,
        "scheduler_mutation_performed": False,
        "autonomy_loop_started": False,
        "repair_started": False,
    }


def build_runtime_progress_memory_milestone_seal(
    commit_history: list[Any] | None,
    *,
    runtime_id: str | None = None,
    total_steps: int | None = None,
) -> dict[str, Any]:
    audit = build_runtime_progress_memory_audit_record(
        commit_history, runtime_id=runtime_id, total_steps=total_steps
    )
    snapshot = _as_mapping(audit.get("progress_snapshot"))
    return {
        "seal": "runtime_progress_memory_bundle",
        "schema": RUNTIME_PROGRESS_MEMORY_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_RUNTIME_PROGRESS_MEMORY_AND_RESUME_CURSOR_RECORDS_ONLY",
        "runtime_id": snapshot.get("runtime_id"),
        "progress_snapshot_id": snapshot.get("progress_snapshot_id"),
        "resume_cursor": _as_mapping(snapshot.get("resume_cursor")),
        "recovery_required": snapshot.get("recovery_required") is True,
        "commit_history_only": True,
        "task_execution_performed": False,
        "executor_run_performed": False,
        "scheduler_mutation_performed": False,
        "autonomy_loop_started": False,
        "repair_started": False,
        "forbidden_surfaces_locked": True,
    }


__all__ = [
    "RUNTIME_PROGRESS_MEMORY_SCHEMA",
    "PROGRESS_COMMIT_STATUSES",
    "build_runtime_progress_snapshot",
    "build_runtime_progress_memory_audit_projection",
    "build_runtime_progress_memory_audit_record",
    "build_runtime_progress_memory_milestone_seal",
]
