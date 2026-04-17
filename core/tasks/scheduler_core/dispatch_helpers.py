from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


def execute_dispatch_round(
    scheduler: Any,
    dispatch_results: List[Any],
    current_tick: int,
) -> List[Dict[str, Any]]:
    round_executed: List[Dict[str, Any]] = []

    for dispatch_result in dispatch_results:
        handled = scheduler._handle_dispatch_result(
            dispatch_result=dispatch_result,
            current_tick=current_tick,
        )
        if handled is not None:
            round_executed.append(handled)

    return round_executed


def handle_dispatch_result(
    scheduler: Any,
    dispatch_result: Any,
    current_tick: int,
    terminal_statuses: Set[str],
) -> Optional[Dict[str, Any]]:
    if not getattr(dispatch_result, "dispatched", False) or getattr(dispatch_result, "task", None) is None:
        return None

    scheduled_task = dispatch_result.task
    task_id = str(getattr(scheduled_task, "task_id", "") or "").strip()
    if not task_id:
        return None

    repo_task = scheduler._get_task_from_repo(task_id)
    if not isinstance(repo_task, dict):
        return scheduler._handle_missing_repo_task(task_id=task_id)

    repo_task = scheduler._hydrate_task_from_workspace(repo_task)
    current_status = str(repo_task.get("status") or "").strip().lower()
    if current_status in terminal_statuses:
        scheduler.worker_pool.release_by_task(task_id)
        return {
            "ok": True,
            "task_id": task_id,
            "status": current_status,
            "message": "task already terminal, skipped",
        }

    try:
        runner_result = scheduler.run_one_step(task=repo_task, current_tick=current_tick)
    except Exception as e:
        return scheduler._handle_run_one_step_exception(task_id=task_id, error=e)

    return scheduler._finalize_dispatched_task(
        dispatch_result=dispatch_result,
        repo_task=repo_task,
        runner_result=runner_result,
    )


def handle_missing_repo_task(
    scheduler: Any,
    task_id: str,
    status_failed: str,
) -> Dict[str, Any]:
    scheduler.dispatcher.fail_task(
        task_id=task_id,
        error="task missing from repository",
        requeue_on_retry=False,
    )
    scheduler._mark_repo_task_failed(task_id=task_id, error="task missing from repository")
    return {
        "ok": False,
        "task_id": task_id,
        "status": status_failed,
        "error": "task missing from repository",
    }


def handle_run_one_step_exception(
    scheduler: Any,
    task_id: str,
    error: Exception,
    status_failed: str,
) -> Dict[str, Any]:
    fail_result = scheduler.dispatcher.fail_task(
        task_id=task_id,
        error=f"run_one_step exception: {error}",
        requeue_on_retry=False,
    )
    scheduler._mark_repo_task_failed(task_id=task_id, error=f"run_one_step exception: {error}")
    return {
        "ok": False,
        "task_id": task_id,
        "status": fail_result.get("final_status", status_failed),
        "error": str(error),
    }


def finalize_dispatched_task(
    scheduler: Any,
    dispatch_result: Any,
    repo_task: Dict[str, Any],
    runner_result: Dict[str, Any],
    status_blocked: str,
    status_finished: str,
    status_failed: str,
) -> Dict[str, Any]:
    scheduled_task = dispatch_result.task
    task_id = str(getattr(scheduled_task, "task_id", "") or "").strip()

    refreshed_repo_task = scheduler._get_task_from_repo(task_id)
    effective_status, effective_final_answer = scheduler._extract_effective_status_and_answer(
        original_task=repo_task,
        refreshed_task=refreshed_repo_task,
        runner_result=runner_result,
    )

    if effective_status in {"done", "finished", status_finished, "success", "completed"}:
        scheduler.dispatcher.complete_task(task_id=task_id, result=effective_final_answer)
        scheduler._mark_repo_task_finished(task_id=task_id, result=effective_final_answer)

    elif effective_status in {"failed", status_failed, "error"}:
        fail_error = str(
            (runner_result or {}).get("error")
            or effective_final_answer
            or "task failed"
        )
        scheduler.dispatcher.fail_task(
            task_id=task_id,
            error=fail_error,
            requeue_on_retry=False,
        )
        scheduler._mark_repo_task_failed(task_id=task_id, error=fail_error)

    elif effective_status in {status_blocked}:
        scheduler.worker_pool.release_by_task(task_id)
        blocked_reason = str((runner_result or {}).get("blocked_reason") or "")
        scheduler._sync_blocked_state(task_id=task_id, blocked_reason=blocked_reason)

    elif effective_status in {"queued", "retry", "ready", "running"}:
        scheduler.worker_pool.release_by_task(task_id)
        if scheduler._can_requeue_task(task_id):
            scheduler.scheduler_queue.requeue(task_id=task_id, priority=scheduled_task.priority)
            scheduler._mark_repo_task_queued(
                task_id=task_id,
                error=str((runner_result or {}).get("error") or ""),
            )

    else:
        scheduler.worker_pool.release_by_task(task_id)

    return {
        "ok": bool((runner_result or {}).get("ok", True)),
        "task_id": task_id,
        "worker_id": getattr(dispatch_result, "worker_id", None),
        "status": effective_status,
        "final_answer": effective_final_answer,
        "result": runner_result,
    }


def scheduler_dispatch_idle(scheduler: Any) -> bool:
    snapshot = scheduler.dispatcher.snapshot()
    queue_stats = snapshot.get("queue", {})
    worker_stats = snapshot.get("workers", {})
    return (
        int(queue_stats.get("queued_count", 0) or 0) <= 0
        and int(worker_stats.get("running_count", 0) or 0) <= 0
    )


def build_tick_result(
    scheduler: Any,
    scheduler_build: str,
    rounds_used: int,
    total_dispatched: int,
    last_synced: List[str],
    all_executed_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    snapshot = scheduler.dispatcher.snapshot()
    queue_stats = snapshot.get("queue", {})
    worker_stats = snapshot.get("workers", {})

    return {
        "ok": True,
        "scheduler_build": scheduler_build,
        "tick": scheduler.current_tick,
        "rounds_used": rounds_used,
        "max_scheduler_rounds_per_tick": scheduler.max_scheduler_rounds_per_tick,
        "synced_task_ids": last_synced,
        "dispatched_count": total_dispatched,
        "executed_count": len(all_executed_results),
        "executed_results": all_executed_results,
        "snapshot": {
            "queue": queue_stats,
            "workers": worker_stats,
            "queued_count": queue_stats.get("queued_count", 0),
            "total_count": queue_stats.get("total_count", 0),
            "running_count": worker_stats.get("running_count", 0),
            "ready_queue": scheduler.dispatcher.list_queued(),
            "running_tasks": scheduler.dispatcher.list_running(),
        },
    }
