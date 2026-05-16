from __future__ import annotations

from typing import Any, Dict, List


REVIEW_PENDING_STATUSES = {
    "pending",
    "required",
    "requested",
    "waiting",
    "waiting_review",
    "review_required",
    "pending_review",
}

REVIEW_CLOSED_STATUSES = {
    "approved",
    "accepted",
    "allowed",
    "cleared",
    "resolved",
    "rejected",
    "denied",
    "declined",
    "cancelled",
    "canceled",
}


def build_queue_rows_payload(
    *,
    dispatcher: Any,
    scheduler_build: str,
    current_tick: int,
) -> Dict[str, Any]:
    queued_rows = dispatcher.list_queued()
    return {
        "ok": True,
        "scheduler_build": scheduler_build,
        "tick": current_tick,
        "count": len(queued_rows),
        "rows": [
            {
                "task_id": row.get("task_id"),
                "status": row.get("status"),
                "priority": row.get("priority"),
                "current_step_index": row.get("current_step_index"),
            }
            for row in queued_rows
        ],
    }


def is_review_queue_task(task: Dict[str, Any], *, review_required_status: str) -> bool:
    if not isinstance(task, dict):
        return False

    review_status = str(task.get("review_status") or "").strip().lower()
    if review_status in REVIEW_CLOSED_STATUSES:
        return False

    status = str(task.get("status") or "").strip().lower()
    return bool(
        task.get("requires_review", False)
        or task.get("requires_approval", False)
        or status == review_required_status
        or review_status in REVIEW_PENDING_STATUSES
    )


def build_queue_snapshot_payload(
    *,
    dispatcher: Any,
    worker_pool: Any,
    repo_tasks: List[Dict[str, Any]],
    scheduler_build: str,
    current_tick: int,
    review_required_status: str,
    workspace_dir: str,
    workspace_root: str,
    shared_dir: str,
) -> Dict[str, Any]:
    ready_queue = dispatcher.list_queued()
    running_tasks = dispatcher.list_running()
    review_queue = [
        task for task in repo_tasks
        if is_review_queue_task(task, review_required_status=review_required_status)
    ]

    return {
        "ok": True,
        "scheduler_build": scheduler_build,
        "tick": current_tick,
        "ready_queue": ready_queue,
        "ready_queue_size": len(ready_queue),
        "running_tasks": running_tasks,
        "running_count": len(running_tasks),
        "review_queue": review_queue,
        "review_queue_size": len(review_queue),
        "worker_pool": worker_pool.stats(),
        "workspace_dir": workspace_dir,
        "workspace_root": workspace_root,
        "shared_dir": shared_dir,
        "tasks": repo_tasks,
        "task_count": len(repo_tasks),
    }
