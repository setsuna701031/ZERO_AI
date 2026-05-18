from __future__ import annotations

from typing import Any


def release_worker_for_task(scheduler: Any, task_id: str) -> bool:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        return False

    try:
        scheduler.worker_pool.release_by_task(normalized_task_id)
    except Exception:
        return False
    return True


__all__ = ["release_worker_for_task"]
