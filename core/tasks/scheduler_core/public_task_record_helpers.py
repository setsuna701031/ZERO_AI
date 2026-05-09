from __future__ import annotations

import copy
import os
import time
from typing import Any, Dict, Optional

from core.planning.replan_suggestion import (
    build_replan_suggestion,
    build_replan_suggestions,
    format_replan_suggestion_cli,
)
from core.tasks.scheduler_core.repo_state_helpers import sync_runtime_back_to_repo


def build_public_task_record(
    *,
    scheduler: Any,
    task: Dict[str, Any],
    status_created: str = "created",
    default_max_replans: int = 3,
) -> Dict[str, Any]:
    """Build the public task snapshot payload for CLI/UI consumers.

    This helper owns public-record formatting.  The scheduler remains the
    orchestration shell and provides the small scheduler-specific adapters
    needed for normalization and logical path conversion.
    """
    normalized = scheduler._normalize_task_schema(task)
    normalized = scheduler._backfill_replan_decision_fields(normalized)
    normalized = scheduler._infer_completion_fields(normalized)
    normalized = scheduler._clear_stale_replan_fields(normalized)

    result_path = str(normalized.get("result_path") or "")
    result_logical_path = str(normalized.get("result_logical_path") or "")
    if result_path and not result_logical_path:
        result_logical_path = scheduler._to_logical_path(result_path)

    open_targets = copy.deepcopy(normalized.get("open_targets", [])) if isinstance(normalized.get("open_targets"), list) else []
    artifacts = copy.deepcopy(normalized.get("artifacts", [])) if isinstance(normalized.get("artifacts"), list) else []
    if open_targets and not artifacts:
        artifacts = copy.deepcopy(open_targets)

    record = {
        "task_id": scheduler._extract_task_id(normalized),
        "goal": str(normalized.get("goal") or ""),
        "status": str(normalized.get("status") or status_created),
        "current_step_index": int(normalized.get("current_step_index", 0) or 0),
        "steps_total": int(normalized.get("steps_total", len(normalized.get("steps", []))) or 0),
        "current_step": copy.deepcopy(normalized.get("current_step")) if isinstance(normalized.get("current_step"), dict) else None,
        "final_answer": str(normalized.get("final_answer") or ""),
        "last_error": str(normalized.get("last_error") or ""),
        "blocked_reason": str(normalized.get("blocked_reason") or ""),
        "waiting_reason": str(normalized.get("waiting_reason") or ""),
        "state_detail": str(normalized.get("state_detail") or ""),
        "next_action": str(normalized.get("next_action") or ""),
        "terminal_reason": str(normalized.get("terminal_reason") or ""),
        "last_decision": str(normalized.get("last_decision") or ""),
        "last_decision_reason": str(normalized.get("last_decision_reason") or ""),
        "loop_cycle_count": int(normalized.get("loop_cycle_count", 0) or 0),
        "blockers": copy.deepcopy(normalized.get("blockers", [])) if isinstance(normalized.get("blockers"), list) else [],
        "active_blocker_count": int(normalized.get("active_blocker_count", 0) or 0),
        "requires_review": bool(normalized.get("requires_review", False)),
        "review_status": str(normalized.get("review_status") or ""),
        "review_id": str(normalized.get("review_id") or ""),
        "agent_action": str(normalized.get("agent_action") or ""),
        "result_path": result_path,
        "result_logical_path": result_logical_path,
        "result_exists": bool(normalized.get("result_exists")),
        "openable": bool(normalized.get("openable")),
        "task_dir": str(normalized.get("task_dir") or ""),
        "task_dir_logical_path": scheduler._to_logical_path(str(normalized.get("task_dir") or "")),
        "plan_file": str(normalized.get("plan_file") or ""),
        "plan_file_logical_path": scheduler._to_logical_path(str(normalized.get("plan_file") or "")),
        "runtime_state_file": str(normalized.get("runtime_state_file") or ""),
        "runtime_state_file_logical_path": scheduler._to_logical_path(str(normalized.get("runtime_state_file") or "")),
        "trace_file": str(normalized.get("trace_file") or ""),
        "trace_file_logical_path": scheduler._to_logical_path(str(normalized.get("trace_file") or "")),
        "execution_log_file": str(normalized.get("execution_log_file") or ""),
        "execution_log_file_logical_path": scheduler._to_logical_path(str(normalized.get("execution_log_file") or "")),
        "updated_at": int(normalized.get("updated_at", 0) or 0),
        "task_type": str(normalized.get("task_type") or ""),
        "source": str(normalized.get("source") or ""),
        "requires_approval": bool(normalized.get("requires_approval", False)),
        "l5_trigger": copy.deepcopy(normalized.get("l5_trigger", {})) if isinstance(normalized.get("l5_trigger"), dict) else {},
        "replan_count": int(normalized.get("replan_count", 0) or 0),
        "max_replans": int(normalized.get("max_replans", default_max_replans) or default_max_replans),
        "replanned": bool(normalized.get("replanned", False)),
        "replan_reason": str(normalized.get("replan_reason") or ""),
        "replan_decision": str(normalized.get("replan_decision") or ""),
        "replan_summary": str(normalized.get("replan_summary") or ""),
        "replan_failed_step_type": str(normalized.get("replan_failed_step_type") or ""),
        "replan_repairable": normalized.get("replan_repairable", None),
        "completion_mode": str(normalized.get("completion_mode") or ""),
        "verification_required": normalized.get("verification_required", None),
        "verification_passed": normalized.get("verification_passed", None),
        "history": copy.deepcopy(normalized.get("history", [])) if isinstance(normalized.get("history"), list) else [],
        "open_targets": open_targets,
        "artifacts": artifacts,
    }
    suggestion = build_replan_suggestion(normalized)
    suggestions = [suggestion] if suggestion else []
    record["replan_suggestion"] = suggestion
    record["suggestions"] = suggestions
    record["cli_suggestion"] = format_replan_suggestion_cli(suggestion)
    return record


def refresh_task_public_fields(
    *,
    scheduler: Any,
    task: Dict[str, Any],
    status_created: str = "created",
    default_max_replans: int = 3,
) -> Dict[str, Any]:
    """Refresh derived public fields on a task payload.

    This keeps artifact/public snapshot formatting outside the scheduler while
    still using scheduler-owned path and task-schema helpers during Phase9.
    """
    if not isinstance(task, dict):
        return task

    task = scheduler._normalize_task_schema(task)

    if not isinstance(task.get("results"), list):
        task["results"] = []
    if not isinstance(task.get("step_results"), list):
        task["step_results"] = copy.deepcopy(task.get("results", []))
    if task.get("last_step_result") is None and task.get("step_results"):
        try:
            task["last_step_result"] = copy.deepcopy(task["step_results"][-1])
        except Exception:
            pass
    if not isinstance(task.get("execution_log"), list):
        task["execution_log"] = []

    if task["status"] in {"finished", "done", "success", "completed"} and not str(task.get("final_answer") or "").strip():
        task["final_answer"] = scheduler._build_simple_final_answer(task.get("results", []))

    artifact_paths = scheduler._extract_result_artifact_paths(task)
    artifact_entries = [scheduler._make_artifact_entry(path) for path in artifact_paths]

    preferred_result_path = ""
    for entry in artifact_entries:
        path = str(entry.get("path") or "").strip()
        if not path:
            continue
        if path.endswith("result.json") and entry.get("exists"):
            preferred_result_path = path
            break
    if not preferred_result_path:
        for entry in artifact_entries:
            if bool(entry.get("exists")) and os.path.isfile(str(entry.get("path") or "")):
                preferred_result_path = str(entry.get("path") or "")
                break
    if not preferred_result_path and artifact_entries:
        preferred_result_path = str(artifact_entries[0].get("path") or "")

    result_exists = bool(preferred_result_path and os.path.exists(preferred_result_path))
    if not result_exists:
        result_exists = bool(
            str(task.get("final_answer") or "").strip()
            or task.get("results")
            or task.get("execution_log")
        )

    openable = bool(
        result_exists
        or any(bool(entry.get("exists")) for entry in artifact_entries)
        or os.path.exists(str(task.get("task_dir") or ""))
    )

    try:
        updated_at = int(time.time())
    except Exception:
        updated_at = 0

    task["result_path"] = preferred_result_path
    task["result_logical_path"] = scheduler._to_logical_path(preferred_result_path)
    task["result_exists"] = result_exists
    task["openable"] = openable
    task["open_targets"] = artifact_entries
    task["artifacts"] = copy.deepcopy(artifact_entries)
    task["updated_at"] = updated_at
    suggestion = build_replan_suggestion(task)
    task["replan_suggestion"] = suggestion
    task["suggestions"] = build_replan_suggestions(task)
    task["cli_suggestion"] = format_replan_suggestion_cli(suggestion)

    task = scheduler._infer_completion_fields(task)
    task = scheduler._clear_stale_replan_fields(task)
    task["public_snapshot"] = build_public_task_record(
        scheduler=scheduler,
        task=task,
        status_created=status_created,
        default_max_replans=default_max_replans,
    )

    return task


def sync_runtime_back_to_repo_with_retry_collapse(
    *,
    scheduler: Any,
    task: Dict[str, Any],
    runner_result: Optional[Dict[str, Any]] = None,
) -> None:
    """Sync runtime state back to the repo and apply retry-collapse policy."""
    sync_runtime_back_to_repo(
        scheduler=scheduler,
        task=task,
        runner_result=runner_result,
    )
    scheduler._collapse_non_retryable_retrying_task(
        task=task,
        runner_result=runner_result,
    )
