from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.tasks.scheduler_core.dispatch_runtime_router import route_enqueue_repo_task_if_ready
from core.tasks.scheduler_core.dispatch_worker_release import release_worker_for_task as route_worker_release
from core.tasks.scheduler_core.public_task_record_helpers import sync_runtime_back_to_repo_with_retry_collapse
from core.tasks.scheduler_core.task_scheduler_queue import STATUS_QUEUED, ScheduledTask


def cancel_ready_queue_task(scheduler: Any, task_id: str) -> None:
    try:
        scheduler.scheduler_queue.cancel(task_id)
    except Exception:
        pass
    route_worker_release(scheduler, task_id)
    scheduler._emit_scheduler_evidence(
        "cancelled",
        task_id=task_id,
        queue_name="ready",
        reason="ready_queue_cancel",
    )


def emit_scheduler_evidence(
    scheduler: Any,
    phase: str,
    *,
    task_id: str,
    queue_name: str = "ready",
    reason: Any = None,
) -> None:
    adapter = getattr(scheduler, "evidence_adapter", None)
    if adapter is None:
        return

    phase_name = str(phase or "").strip().lower()
    method_name = {
        "enqueued": "emit_enqueued",
        "dequeued": "emit_dequeued",
        "dispatched": "emit_dispatched",
        "requeued": "emit_requeued",
        "cancelled": "emit_cancelled",
    }.get(phase_name)
    if not method_name:
        return

    method = getattr(adapter, method_name, None)
    if not callable(method):
        return

    scheduler_id = str(getattr(scheduler, "scheduler_id", "") or "scheduler")
    clean_task_id = str(task_id or "").strip()
    clean_queue_name = str(queue_name or "ready").strip() or "ready"
    if not clean_task_id:
        return

    try:
        if phase_name in {"requeued", "cancelled"}:
            method(scheduler_id, clean_task_id, clean_queue_name, reason)
        else:
            method(scheduler_id, clean_task_id, clean_queue_name)
    except Exception:
        return


def can_requeue_task(scheduler: Any, task_id: str, *, terminal_statuses: set[str]) -> bool:
    task = scheduler._get_task_from_repo(task_id)
    if not isinstance(task, dict):
        return False

    status = str(task.get("status") or "").strip().lower()
    if status in terminal_statuses:
        return False

    deps_ready, _ = scheduler._task_dependencies_satisfied(task)
    return deps_ready


def queue_contains_task(scheduler: Any, task_id: str) -> bool:
    try:
        return bool(scheduler.scheduler_queue.contains(str(task_id or "").strip()))
    except Exception:
        return False


def repo_task_to_scheduled_task(
    scheduler: Any,
    task: Dict[str, Any],
    *,
    scheduler_build: str,
) -> ScheduledTask:
    task_id = scheduler._extract_task_id(task)
    return ScheduledTask(
        task_id=task_id,
        title=str(task.get("title") or task.get("goal") or task_id),
        priority=scheduler._safe_int_for_runtime_gate(task.get("priority"), 0),
        status=str(task.get("status") or STATUS_QUEUED),
        retry_count=scheduler._safe_int_for_runtime_gate(task.get("retry_count"), 0),
        max_retries=scheduler._safe_int_for_runtime_gate(task.get("max_retries"), 0),
        payload=copy.deepcopy(task),
        metadata={
            "task_name": str(task.get("task_name") or task_id),
            "scheduler_build": scheduler_build,
        },
        last_error=task.get("last_error"),
    )


def sync_runner_result_and_requeue_if_ready(
    scheduler: Any,
    *,
    task: Dict[str, Any],
    runner_result: Dict[str, Any],
    status_queued: str,
) -> None:
    runner_result = scheduler._attach_orchestration_summary_to_runner_result(task=task, runner_result=runner_result)
    sync_runtime_back_to_repo_with_retry_collapse(scheduler=scheduler, task=task, runner_result=runner_result)

    refreshed_task = scheduler._get_task_from_repo(scheduler._extract_task_id(task))
    if not isinstance(refreshed_task, dict):
        return

    refreshed_status = str(refreshed_task.get("status") or "").strip().lower()
    if refreshed_status in {"queued", status_queued, "retry", "ready"}:
        requeued = route_enqueue_repo_task_if_ready(scheduler, refreshed_task, overwrite=True)
        if requeued:
            scheduler._emit_scheduler_evidence(
                "requeued",
                task_id=scheduler._extract_task_id(refreshed_task),
                queue_name="ready",
                reason=refreshed_status,
            )
