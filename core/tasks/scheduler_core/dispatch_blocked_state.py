from __future__ import annotations

from typing import Any

from core.tasks.scheduler_core.dispatch_state_transition import (
    sync_blocked_state,
    sync_unblocked_state,
)


def apply_blocked_state(
    scheduler: Any,
    task_id: str,
    blocked_reason: str = "",
) -> bool:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        return False

    try:
        sync_blocked_state(
            scheduler=scheduler,
            task_id=normalized_task_id,
            blocked_reason=blocked_reason,
        )
    except Exception:
        return False
    return True


def apply_unblocked_state(scheduler: Any, task_id: str) -> bool:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        return False

    try:
        sync_unblocked_state(scheduler=scheduler, task_id=normalized_task_id)
    except Exception:
        return False
    return True


__all__ = [
    "apply_blocked_state",
    "apply_unblocked_state",
]
