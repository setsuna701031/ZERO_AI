from __future__ import annotations

import copy
import os
from typing import Any, Dict, Optional

from core.tasks.scheduler_core.repo_blocked_state import (
    _downgrade_advisory_blocked_status,
    sync_blocked_state,
    sync_unblocked_state,
)
from core.tasks.scheduler_core.repo_runtime_adapter import build_repo_runtime_state_adapter_payload
from core.tasks.scheduler_core.repo_task_state import (
    mark_repo_task_failed,
    mark_repo_task_finished,
    mark_repo_task_queued,
)


LOOP_STATE_KEYS = (
    "last_observation",
    "last_decision",
    "last_decision_reason",
    "next_action",
    "terminal_reason",
    "loop_cycle_count",
    "loop_history",
)

REVIEW_STATE_KEYS = (
    "review_id",
    "review_status",
    "requires_review",
    "agent_action",
    "review_payload",
)


def _save_runtime_state_from_merged(scheduler: Any, merged: Dict[str, Any]) -> None:
    runtime = getattr(scheduler, "task_runtime", None)
    if runtime is None:
        return

    save_fn = getattr(runtime, "save_runtime_state", None)
    if not callable(save_fn):
        return

    state_payload: Dict[str, Any] = copy.deepcopy(merged)

    load_fn = getattr(runtime, "load_runtime_state", None)
    if callable(load_fn):
        try:
            loaded = load_fn(merged)
            if isinstance(loaded, dict):
                loaded.update(copy.deepcopy(merged))
                state_payload = loaded
        except Exception:
            pass

    try:
        save_fn(merged, state_payload)
    except Exception:
        pass


def _sync_loop_fields_into_merged(merged: Dict[str, Any], source: Dict[str, Any]) -> None:
    for key in LOOP_STATE_KEYS:
        if key in source:
            merged[key] = copy.deepcopy(source.get(key))


def _sync_review_fields_into_merged(merged: Dict[str, Any], source: Dict[str, Any]) -> None:
    for key in REVIEW_STATE_KEYS:
        if key in source:
            merged[key] = copy.deepcopy(source.get(key))


def _select_effective_task_payload(task: Dict[str, Any], runner_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    effective = copy.deepcopy(task if isinstance(task, dict) else {})
    if isinstance(runner_result, dict):
        runner_task = runner_result.get("task")
        if isinstance(runner_task, dict):
            effective.update(copy.deepcopy(runner_task))
    return effective


def _resolve_repo_runtime_task_id(task: Dict[str, Any]) -> str:
    return str(
        task.get("task_id")
        or task.get("task_name")
        or task.get("id")
        or ""
    ).strip()


def _load_repo_runtime_base_task(scheduler: Any, task_id: str, effective_task: Dict[str, Any]) -> Dict[str, Any]:
    repo_task = scheduler._get_task_from_repo(task_id)
    base_task = copy.deepcopy(repo_task if isinstance(repo_task, dict) else effective_task)
    base_task = scheduler._hydrate_task_from_workspace(base_task)
    _sync_loop_fields_into_merged(base_task, effective_task)
    _sync_review_fields_into_merged(base_task, effective_task)
    return base_task


def _load_repo_runtime_state_for_task(scheduler: Any, base_task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    runtime_state = None
    if scheduler.task_runtime is not None and hasattr(scheduler.task_runtime, "load_runtime_state"):
        try:
            runtime_state = scheduler.task_runtime.load_runtime_state(base_task)
        except Exception:
            runtime_state = None
    return runtime_state


def _merge_repo_runtime_state_fields(merged: Dict[str, Any], runtime_state: Optional[Dict[str, Any]]) -> None:
    if isinstance(runtime_state, dict):
        for key in (
            "status", "priority", "retry_count", "max_retries", "retry_delay", "next_retry_tick", "timeout_ticks",
            "wait_until_tick", "created_tick", "last_run_tick", "last_failure_tick", "finished_tick", "depends_on",
            "blocked_reason", "failure_type", "failure_message", "last_error", "final_answer", "cancel_requested",
            "cancel_reason", "current_step_index", "steps", "steps_total", "results", "step_results",
            "last_step_result", "replan_count", "replanned", "replan_reason", "replan_decision", "replan_summary",
            "replan_failed_step_type", "replan_repairable", "completion_mode", "verification_required",
            "verification_passed", "max_replans", "planner_result", "history", "execution_log", "result_file",
            "execution_log_file", "plan_file", "log_file", "runtime_state_file", "trace_file", "workspace_root",
            "workspace_dir", "shared_dir", "task_dir", "scheduler_build",
        ):
            if key in runtime_state:
                merged[key] = copy.deepcopy(runtime_state.get(key))
        _sync_loop_fields_into_merged(merged, runtime_state)
        _sync_review_fields_into_merged(merged, runtime_state)


def _merge_repo_runtime_runner_result_fields(
    merged: Dict[str, Any],
    runner_result: Optional[Dict[str, Any]],
) -> None:
    if isinstance(runner_result, dict):
        for key in (
            "status", "final_answer", "execution_log", "results", "step_results", "last_step_result",
            "current_step_index", "steps_total", "last_run_tick", "last_failure_tick", "finished_tick",
            "blocked_reason", "replan_decision", "replan_summary", "replan_failed_step_type",
            "replan_repairable", "completion_mode", "verification_required", "verification_passed",
        ):
            if key in runner_result:
                merged[key] = copy.deepcopy(runner_result.get(key))
        _sync_loop_fields_into_merged(merged, runner_result)
        _sync_review_fields_into_merged(merged, runner_result)

        runner_task = runner_result.get("task")
        if isinstance(runner_task, dict):
            _sync_loop_fields_into_merged(merged, runner_task)
            _sync_review_fields_into_merged(merged, runner_task)


def _apply_repo_runtime_replan_projection(
    merged: Dict[str, Any],
    runner_result: Optional[Dict[str, Any]],
) -> None:
    if isinstance(runner_result, dict):
        replan_result = runner_result.get("replan_result")
        if isinstance(replan_result, dict) and bool(replan_result.get("replanned")):
            raw_replan_result = replan_result.get("raw_replan_result", {})
            plan = raw_replan_result.get("plan", {}) if isinstance(raw_replan_result, dict) else {}
            new_steps = plan.get("steps", []) if isinstance(plan, dict) else []

            if isinstance(new_steps, list) and new_steps:
                merged["steps"] = copy.deepcopy(new_steps)
                merged["steps_total"] = len(new_steps)
                merged["current_step_index"] = 0
            else:
                merged["current_step_index"] = 0

            merged["replanned"] = True
            merged["replan_count"] = int(replan_result.get("replan_count", merged.get("replan_count", 0)) or 0)
            merged["planner_result"] = copy.deepcopy(plan) if isinstance(plan, dict) else {}
            merged["replan_reason"] = str(
                runner_result.get("replan_reason")
                or merged.get("last_error")
                or merged.get("failure_message")
                or ""
            )

            status_from_runner = str(runner_result.get("status") or "").strip().lower()
            if status_from_runner:
                merged["status"] = status_from_runner


def sync_runtime_back_to_repo(
    scheduler: Any,
    task: Dict[str, Any],
    runner_result: Optional[Dict[str, Any]] = None,
) -> None:
    task_id = _resolve_repo_runtime_task_id(task)
    if not task_id:
        return

    effective_task = _select_effective_task_payload(task=task, runner_result=runner_result)
    base_task = _load_repo_runtime_base_task(
        scheduler=scheduler,
        task_id=task_id,
        effective_task=effective_task,
    )
    runtime_state = _load_repo_runtime_state_for_task(scheduler=scheduler, base_task=base_task)
    merged = copy.deepcopy(base_task)
    _merge_repo_runtime_state_fields(merged=merged, runtime_state=runtime_state)

    _sync_loop_fields_into_merged(merged, task)
    _sync_review_fields_into_merged(merged, task)
    _merge_repo_runtime_runner_result_fields(merged=merged, runner_result=runner_result)
    _apply_repo_runtime_replan_projection(merged=merged, runner_result=runner_result)

    if not isinstance(merged.get("results"), list):
        merged["results"] = []
    if not isinstance(merged.get("step_results"), list):
        merged["step_results"] = copy.deepcopy(merged.get("results", []))

    if merged.get("last_step_result") is None and merged.get("step_results"):
        try:
            merged["last_step_result"] = copy.deepcopy(merged["step_results"][-1])
        except Exception:
            pass

    steps = merged.get("steps", [])
    if isinstance(steps, list):
        merged["steps_total"] = int(merged.get("steps_total", len(steps)) or len(steps))
    else:
        merged["steps_total"] = int(merged.get("steps_total", 0) or 0)

    if merged.get("current_step_index") is None:
        merged["current_step_index"] = 0

    merged["task_name"] = merged.get("task_name") or task_id
    merged["task_dir"] = merged.get("task_dir") or os.path.join(scheduler.tasks_root, task_id)
    merged["plan_file"] = merged.get("plan_file") or os.path.join(merged["task_dir"], "plan.json")
    merged["runtime_state_file"] = merged.get("runtime_state_file") or os.path.join(merged["task_dir"], "runtime_state.json")
    merged["trace_file"] = merged.get("trace_file") or os.path.join(merged["task_dir"], "trace.json")
    merged["workspace_root"] = merged.get("workspace_root") or scheduler.workspace_root
    merged["workspace_dir"] = merged.get("workspace_dir") or scheduler.tasks_root
    merged["shared_dir"] = merged.get("shared_dir") or scheduler.shared_dir
    merged["scheduler_build"] = scheduler.SCHEDULER_BUILD if hasattr(scheduler, "SCHEDULER_BUILD") else getattr(scheduler, "scheduler_build", "")

    merged.setdefault("last_observation", {})
    merged.setdefault("last_decision", "")
    merged.setdefault("last_decision_reason", "")
    merged.setdefault("next_action", "")
    merged.setdefault("terminal_reason", "")
    merged["loop_cycle_count"] = int(merged.get("loop_cycle_count", 0) or 0)
    if not isinstance(merged.get("loop_history"), list):
        merged["loop_history"] = []
    merged.setdefault("review_id", "")
    merged.setdefault("review_status", "")
    merged.setdefault("requires_review", False)
    merged.setdefault("transaction_state", "")
    merged.setdefault("allowed_next_action", "")
    merged.setdefault("approval_required", bool(merged.get("requires_approval", False)))
    merged.setdefault("agent_action", "")
    if not isinstance(merged.get("review_payload"), dict):
        merged["review_payload"] = {}

    inferred_replan_result = None
    if isinstance(runner_result, dict):
        maybe_replan = runner_result.get("replan_result")
        if isinstance(maybe_replan, dict):
            inferred_replan_result = maybe_replan

    merged = scheduler._backfill_replan_decision_fields(merged, replan_result=inferred_replan_result)
    merged = scheduler._infer_completion_fields(merged)

    from core.runtime.runtime_authority_seal import is_task_completion_authority

    completion_authority = (
        runner_result.get("task_completion_authority")
        if isinstance(runner_result, dict)
        else None
    )
    completion_authorized = is_task_completion_authority(
        completion_authority,
        task_id=task_id,
    )
    if isinstance(runner_result, dict):
        runner_action = str(runner_result.get("action") or "").strip().lower()
        if runner_action in {"task_finished", "simple_task_finished"} and completion_authorized:
            merged["status"] = "finished"
            merged["blocked_reason"] = ""
            merged["waiting_reason"] = ""
            merged["last_error"] = ""
            merged["failure_message"] = ""
            try:
                steps_total_value = int(merged.get("steps_total", 0) or 0)
            except Exception:
                steps_total_value = 0
            if steps_total_value <= 0 and isinstance(merged.get("steps"), list):
                steps_total_value = len(merged.get("steps") or [])
            try:
                current_index_value = int(merged.get("current_step_index", 0) or 0)
            except Exception:
                current_index_value = 0
            if steps_total_value > 0:
                merged["steps_total"] = steps_total_value
                merged["current_step_index"] = max(current_index_value, steps_total_value)
            if not str(merged.get("final_answer") or "").strip():
                merged["final_answer"] = str(runner_result.get("final_answer") or "task finished")

    merged = scheduler._clear_stale_replan_fields(merged)
    merged = scheduler._refresh_task_public_fields(merged)
    merged = _downgrade_advisory_blocked_status(merged)
    merged = build_repo_runtime_state_adapter_payload(merged=merged, runner_result=runner_result)
    _save_runtime_state_from_merged(scheduler, merged)
    scheduler._persist_task_payload(
        task_id=task_id,
        task=merged,
        completion_authority=completion_authority if completion_authorized else None,
    )

    normalized_status = str(merged.get("status") or "").strip().lower()
    if not normalized_status:
        return

    if (
        normalized_status in {"finished", "done", "success", "completed", scheduler.STATUS_FINISHED}
        and completion_authorized
    ):
        final_answer = merged.get("final_answer", "")
        mark_repo_task_finished(
            scheduler=scheduler,
            task_id=task_id,
            result=final_answer,
            completion_authority=completion_authority,
        )
        return

    if normalized_status in {"failed", "error", scheduler.STATUS_FAILED}:
        final_error = str(
            merged.get("last_error")
            or merged.get("failure_message")
            or (runner_result or {}).get("error")
            or "task failed"
        )
        mark_repo_task_failed(scheduler=scheduler, task_id=task_id, error=final_error)
        return

    if normalized_status in {scheduler.STATUS_BLOCKED, "blocked"}:
        blocked_reason = str(merged.get("blocked_reason") or "")
        sync_blocked_state(scheduler=scheduler, task_id=task_id, blocked_reason=blocked_reason)
        return

    if normalized_status in {"queued", scheduler.STATUS_QUEUED, "ready", "retry"}:
        queue_error = str(merged.get("last_error") or merged.get("failure_message") or "")
        mark_repo_task_queued(scheduler=scheduler, task_id=task_id, error=queue_error)
        return

    if normalized_status in {"running"}:
        sync_unblocked_state(scheduler=scheduler, task_id=task_id)
        return
