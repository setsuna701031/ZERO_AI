from __future__ import annotations

import copy
import os
from typing import Any, Dict, List, Optional, Tuple


def extract_effective_status_and_answer(
    original_task: Optional[Dict[str, Any]],
    refreshed_task: Optional[Dict[str, Any]],
    runner_result: Optional[Dict[str, Any]],
) -> Tuple[str, Any]:
    candidates: List[Dict[str, Any]] = []

    if isinstance(runner_result, dict):
        candidates.append(runner_result)
    if isinstance(refreshed_task, dict):
        candidates.append(refreshed_task)
    if isinstance(original_task, dict):
        candidates.append(original_task)

    status = ""
    final_answer: Any = ""

    for source in candidates:
        source_status = str(source.get("status") or "").strip().lower()
        if source_status:
            status = source_status
            break

    for source in candidates:
        if "final_answer" in source:
            value = source.get("final_answer")
            if value not in (None, ""):
                final_answer = value
                break

    return status, final_answer


def mark_repo_task_finished(scheduler: Any, task_id: str, result: Any = None) -> None:
    task = scheduler._get_task_from_repo(task_id)
    if not isinstance(task, dict):
        return

    task["status"] = "finished"
    task["blocked_reason"] = ""
    task["last_error"] = ""
    task["failure_message"] = ""
    task["finished_tick"] = getattr(scheduler, "current_tick", 0)
    task["scheduler_build"] = scheduler.SCHEDULER_BUILD if hasattr(scheduler, 'SCHEDULER_BUILD') else getattr(scheduler, 'scheduler_build', '')

    if result is not None:
        task["final_answer"] = result
    else:
        task["final_answer"] = task.get("final_answer", "")

    task["history"] = scheduler._append_history(task.get("history"), "finished")
    scheduler._persist_task_payload(task_id=task_id, task=task)
    scheduler.worker_pool.release_by_task(task_id)
    scheduler._unblock_tasks_if_dependencies_done()


def mark_repo_task_failed(scheduler: Any, task_id: str, error: str = "") -> None:
    task = scheduler._get_task_from_repo(task_id)
    if not isinstance(task, dict):
        return

    final_error = str(error or task.get("last_error") or task.get("failure_message") or "task failed")

    task["status"] = "failed"
    task["blocked_reason"] = ""
    task["last_error"] = final_error
    task["failure_message"] = final_error
    task["last_failure_tick"] = getattr(scheduler, "current_tick", 0)
    task["scheduler_build"] = scheduler.SCHEDULER_BUILD if hasattr(scheduler, 'SCHEDULER_BUILD') else getattr(scheduler, 'scheduler_build', '')
    task["history"] = scheduler._append_history(task.get("history"), "failed")

    scheduler._persist_task_payload(task_id=task_id, task=task)
    scheduler.worker_pool.release_by_task(task_id)


def mark_repo_task_queued(scheduler: Any, task_id: str, error: str = "") -> None:
    task = scheduler._get_task_from_repo(task_id)
    if not isinstance(task, dict):
        return

    current_status = str(task.get("status") or "").strip().lower()
    if current_status in scheduler.TERMINAL_STATUSES:
        return

    task["status"] = "queued"
    task["blocked_reason"] = ""
    task["scheduler_build"] = scheduler.SCHEDULER_BUILD if hasattr(scheduler, 'SCHEDULER_BUILD') else getattr(scheduler, 'scheduler_build', '')

    final_error = str(error or "").strip()
    if final_error:
        task["last_error"] = final_error
        task["failure_message"] = final_error
    else:
        task["last_error"] = ""
        task["failure_message"] = ""

    task["history"] = scheduler._append_history(task.get("history"), "queued")
    scheduler._persist_task_payload(task_id=task_id, task=task)


def sync_blocked_state(scheduler: Any, task_id: str, blocked_reason: str) -> None:
    task = scheduler._get_task_from_repo(task_id)
    if not isinstance(task, dict):
        return

    current_status = str(task.get("status") or "").strip().lower()
    if current_status in scheduler.TERMINAL_STATUSES:
        return

    final_reason = str(blocked_reason or task.get("blocked_reason") or "").strip()
    changed = False

    if current_status != scheduler.STATUS_BLOCKED:
        task["status"] = scheduler.STATUS_BLOCKED
        task["history"] = scheduler._append_history(task.get("history"), scheduler.STATUS_BLOCKED)
        changed = True

    if str(task.get("blocked_reason") or "") != final_reason:
        task["blocked_reason"] = final_reason
        changed = True

    if str(task.get("last_error") or "") != "":
        task["last_error"] = ""
        changed = True

    if str(task.get("failure_message") or "") != "":
        task["failure_message"] = ""
        changed = True

    build = scheduler.SCHEDULER_BUILD if hasattr(scheduler, 'SCHEDULER_BUILD') else getattr(scheduler, 'scheduler_build', '')
    if str(task.get("scheduler_build") or "") != build:
        task["scheduler_build"] = build
        changed = True

    if changed:
        scheduler._persist_task_payload(task_id=task_id, task=task)

    trace = scheduler._load_trace_for_task(task)
    scheduler._trace_status(
        trace=trace,
        task=task,
        status=scheduler.STATUS_BLOCKED,
        tick=getattr(scheduler, "current_tick", 0),
        final_answer="",
        extra={
            "action": "sync_blocked_state",
            "blocked_reason": str(blocked_reason or ""),
        },
    )
    scheduler._save_trace_for_task(task=task, trace=trace)

    scheduler.worker_pool.release_by_task(task_id)


def sync_unblocked_state(scheduler: Any, task_id: str) -> None:
    task = scheduler._get_task_from_repo(task_id)
    if not isinstance(task, dict):
        return

    current_status = str(task.get("status") or "").strip().lower()
    if current_status in scheduler.TERMINAL_STATUSES:
        return

    changed = False

    if current_status == scheduler.STATUS_BLOCKED:
        task["status"] = "queued"
        task["history"] = scheduler._append_history(task.get("history"), "queued")
        current_status = "queued"
        changed = True

    if str(task.get("blocked_reason") or "") != "":
        task["blocked_reason"] = ""
        changed = True

    if current_status in {"queued", "ready", "retry", scheduler.STATUS_QUEUED}:
        if str(task.get("last_error") or "") != "":
            task["last_error"] = ""
            changed = True
        if str(task.get("failure_message") or "") != "":
            task["failure_message"] = ""
            changed = True

    build = scheduler.SCHEDULER_BUILD if hasattr(scheduler, 'SCHEDULER_BUILD') else getattr(scheduler, 'scheduler_build', '')
    if str(task.get("scheduler_build") or "") != build:
        task["scheduler_build"] = build
        changed = True

    if changed:
        scheduler._persist_task_payload(task_id=task_id, task=task)


def sync_runtime_back_to_repo(
    scheduler: Any,
    task: Dict[str, Any],
    runner_result: Optional[Dict[str, Any]] = None,
) -> None:
    task_id = str(
        task.get("task_id")
        or task.get("task_name")
        or task.get("id")
        or ""
    ).strip()
    if not task_id:
        return

    repo_task = scheduler._get_task_from_repo(task_id)
    base_task = copy.deepcopy(repo_task if isinstance(repo_task, dict) else task)
    base_task = scheduler._hydrate_task_from_workspace(base_task)

    runtime_state = None
    if scheduler.task_runtime is not None and hasattr(scheduler.task_runtime, "load_runtime_state"):
        try:
            runtime_state = scheduler.task_runtime.load_runtime_state(base_task)
        except Exception:
            runtime_state = None

    merged = copy.deepcopy(base_task)

    if isinstance(runtime_state, dict):
        for key in (
            "status","priority","retry_count","max_retries","retry_delay","next_retry_tick","timeout_ticks",
            "wait_until_tick","created_tick","last_run_tick","last_failure_tick","finished_tick","depends_on",
            "blocked_reason","failure_type","failure_message","last_error","final_answer","cancel_requested",
            "cancel_reason","current_step_index","steps","steps_total","results","step_results",
            "last_step_result","replan_count","replanned","replan_reason","replan_decision","replan_summary",
            "replan_failed_step_type","replan_repairable","completion_mode","verification_required",
            "verification_passed","max_replans","planner_result","history","execution_log","result_file",
            "execution_log_file","plan_file","log_file","runtime_state_file","trace_file","workspace_root",
            "workspace_dir","shared_dir","task_dir","scheduler_build",
        ):
            if key in runtime_state:
                merged[key] = copy.deepcopy(runtime_state.get(key))

    if isinstance(runner_result, dict):
        for key in (
            "status","final_answer","execution_log","results","step_results","last_step_result",
            "current_step_index","steps_total","last_run_tick","last_failure_tick","finished_tick",
            "blocked_reason","replan_decision","replan_summary","replan_failed_step_type",
            "replan_repairable","completion_mode","verification_required","verification_passed",
        ):
            if key in runner_result:
                merged[key] = copy.deepcopy(runner_result.get(key))

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
    merged["scheduler_build"] = scheduler.SCHEDULER_BUILD if hasattr(scheduler, 'SCHEDULER_BUILD') else getattr(scheduler, 'scheduler_build', '')

    inferred_replan_result = None
    if isinstance(runner_result, dict):
        maybe_replan = runner_result.get("replan_result")
        if isinstance(maybe_replan, dict):
            inferred_replan_result = maybe_replan

    merged = scheduler._backfill_replan_decision_fields(merged, replan_result=inferred_replan_result)
    merged = scheduler._infer_completion_fields(merged)
    merged = scheduler._clear_stale_replan_fields(merged)
    merged = scheduler._refresh_task_public_fields(merged)
    scheduler._persist_task_payload(task_id=task_id, task=merged)

    normalized_status = str(merged.get("status") or "").strip().lower()
    if not normalized_status:
        return

    if normalized_status in {"finished", "done", "success", "completed", scheduler.STATUS_FINISHED}:
        final_answer = merged.get("final_answer", "")
        mark_repo_task_finished(scheduler=scheduler, task_id=task_id, result=final_answer)
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
