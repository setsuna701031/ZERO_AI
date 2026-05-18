from __future__ import annotations

from typing import Any, Dict


def can_requeue_task(scheduler: Any, task_id: str) -> bool:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        return False

    try:
        return bool(scheduler._can_requeue_task(normalized_task_id))
    except Exception:
        return False


def enqueue_repo_task_if_ready(
    scheduler: Any,
    task: Dict[str, Any],
    overwrite: bool = True,
) -> bool:
    if not isinstance(task, dict):
        return False

    try:
        return bool(scheduler._enqueue_repo_task_if_ready(task, overwrite=overwrite))
    except Exception:
        return False


def sync_runner_result_and_requeue_if_ready(
    scheduler: Any,
    task: Dict[str, Any],
    runner_result: Dict[str, Any],
) -> None:
    if not isinstance(task, dict) or not isinstance(runner_result, dict):
        return

    try:
        scheduler._sync_runner_result_and_requeue_if_ready(
            task=task,
            runner_result=runner_result,
        )
    except Exception:
        return


__all__ = [
    "can_requeue_task",
    "enqueue_repo_task_if_ready",
    "sync_runner_result_and_requeue_if_ready",
]
