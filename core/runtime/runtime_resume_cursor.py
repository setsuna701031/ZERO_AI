from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_RESUME_CURSOR_SCHEMA = "zero.runtime.resume_cursor.v1"

RESUME_CURSOR_STATES = ("CONTINUE", "WAITING", "RECOVERY_REQUIRED", "COMPLETE")


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def decide_runtime_resume_state(
    progress_snapshot: dict[str, Any] | None,
    *,
    total_steps: int | None = None,
) -> str:
    snapshot = _as_mapping(progress_snapshot)
    if snapshot.get("recovery_required") is True:
        return "RECOVERY_REQUIRED"
    completed = snapshot.get("completed_steps")
    skipped = snapshot.get("skipped_steps")
    completed_count = len(completed) if isinstance(completed, list) else 0
    skipped_count = len(skipped) if isinstance(skipped, list) else 0
    if total_steps is not None and completed_count + skipped_count >= total_steps:
        return "COMPLETE"
    if not snapshot.get("last_committed_step"):
        return "WAITING"
    return "CONTINUE"


def build_runtime_resume_cursor(
    progress_snapshot: dict[str, Any] | None,
    *,
    total_steps: int | None = None,
) -> dict[str, Any]:
    snapshot = _as_mapping(progress_snapshot)
    runtime_id = snapshot.get("runtime_id")
    last_step = _as_mapping(snapshot.get("last_committed_step"))
    completed = snapshot.get("completed_steps") if isinstance(snapshot.get("completed_steps"), list) else []
    skipped = snapshot.get("skipped_steps") if isinstance(snapshot.get("skipped_steps"), list) else []
    next_step_index = last_step.get("next_step_index")
    if next_step_index is None:
        next_step_index = len(completed) + len(skipped)
    state = decide_runtime_resume_state(snapshot, total_steps=total_steps)
    cursor_id = "runtime-resume-cursor::" + str(runtime_id or "missing-runtime") + "::" + _stable_fragment(
        {
            "runtime_id": runtime_id,
            "last_step": last_step.get("step_result_commit_id"),
            "next_step_index": next_step_index,
            "state": state,
            "completed_count": len(completed),
            "skipped_count": len(skipped),
            "failed_count": len(snapshot.get("failed_steps", []))
            if isinstance(snapshot.get("failed_steps"), list)
            else 0,
        }
    )
    return {
        "schema": RUNTIME_RESUME_CURSOR_SCHEMA,
        "cursor_id": cursor_id,
        "runtime_id": runtime_id,
        "state": state,
        "next_step_index": next_step_index,
        "last_committed_step": last_step,
        "recovery_required": snapshot.get("recovery_required") is True,
        "record_only": True,
        "cursor_only": True,
        "task_execution_performed": False,
        "executor_run_performed": False,
        "scheduler_mutation_performed": False,
        "autonomy_loop_started": False,
        "repair_started": False,
    }


__all__ = [
    "RUNTIME_RESUME_CURSOR_SCHEMA",
    "RESUME_CURSOR_STATES",
    "decide_runtime_resume_state",
    "build_runtime_resume_cursor",
]
