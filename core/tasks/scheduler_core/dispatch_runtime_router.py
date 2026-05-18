from __future__ import annotations

from typing import Any, Dict

from core.tasks.scheduler_core.dispatch_blocked_state import (
    apply_blocked_state,
    apply_unblocked_state,
)
from core.tasks.scheduler_core.dispatch_requeue import (
    enqueue_repo_task_if_ready,
    sync_runner_result_and_requeue_if_ready,
)
from core.tasks.scheduler_core.dispatch_worker_release import release_worker_for_task


def route_worker_release(scheduler: Any, task_id: str) -> bool:
    return release_worker_for_task(scheduler=scheduler, task_id=task_id)


def route_blocked_state(
    scheduler: Any,
    task_id: str,
    blocked_reason: str = "",
) -> bool:
    return apply_blocked_state(
        scheduler=scheduler,
        task_id=task_id,
        blocked_reason=blocked_reason,
    )


def route_unblocked_state(scheduler: Any, task_id: str) -> bool:
    return apply_unblocked_state(scheduler=scheduler, task_id=task_id)


def route_enqueue_repo_task_if_ready(
    scheduler: Any,
    task: Dict[str, Any],
    overwrite: bool = True,
) -> bool:
    return enqueue_repo_task_if_ready(
        scheduler=scheduler,
        task=task,
        overwrite=overwrite,
    )


def route_sync_runner_result_and_requeue_if_ready(
    scheduler: Any,
    task: Dict[str, Any],
    runner_result: Dict[str, Any],
) -> None:
    sync_runner_result_and_requeue_if_ready(
        scheduler=scheduler,
        task=task,
        runner_result=runner_result,
    )


__all__ = [
    "route_blocked_state",
    "route_enqueue_repo_task_if_ready",
    "route_sync_runner_result_and_requeue_if_ready",
    "route_unblocked_state",
    "route_worker_release",
]
