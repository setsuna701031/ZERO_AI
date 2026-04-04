from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


class TaskStatus:
    """
    ZERO Task 狀態定義（對齊現行 task_runtime / task_runner）

    目標：
    1. 統一狀態名稱
    2. 提供合法轉移規則
    3. 提供 terminal / ready / blocked / runnable 判斷
    4. 讓 scheduler / runner / runtime 都不要再各自手寫狀態邏輯
    """

    CREATED = "created"
    QUEUED = "queued"
    READY = "ready"
    RUNNING = "running"
    RETRYING = "retrying"
    BLOCKED = "blocked"
    WAITING = "waiting"
    PAUSED = "paused"
    FINISHED = "finished"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CANCELED = "canceled"
    TIMEOUT = "timeout"

    NORMALIZED_COMPLETED = "finished"
    NORMALIZED_CANCELLED = "cancelled"

    @classmethod
    def all_status(cls) -> List[str]:
        return [
            cls.CREATED,
            cls.QUEUED,
            cls.READY,
            cls.RUNNING,
            cls.RETRYING,
            cls.BLOCKED,
            cls.WAITING,
            cls.PAUSED,
            cls.FINISHED,
            cls.COMPLETED,
            cls.FAILED,
            cls.CANCELLED,
            cls.CANCELED,
            cls.TIMEOUT,
        ]


TERMINAL_STATES: Set[str] = {
    TaskStatus.FINISHED,
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.CANCELED,
    TaskStatus.TIMEOUT,
}

READY_LIKE_STATES: Set[str] = {
    TaskStatus.QUEUED,
    TaskStatus.READY,
    TaskStatus.RETRYING,
}

BLOCKED_LIKE_STATES: Set[str] = {
    TaskStatus.BLOCKED,
    TaskStatus.WAITING,
}

RUNNABLE_STATES: Set[str] = {
    TaskStatus.QUEUED,
    TaskStatus.READY,
    TaskStatus.RUNNING,
    TaskStatus.RETRYING,
}

# 合法狀態轉移表
VALID_TRANSITIONS: Dict[str, Set[str]] = {
    TaskStatus.CREATED: {
        TaskStatus.QUEUED,
        TaskStatus.READY,
        TaskStatus.BLOCKED,
        TaskStatus.WAITING,
        TaskStatus.CANCELLED,
        TaskStatus.CANCELED,
        TaskStatus.FAILED,
    },
    TaskStatus.QUEUED: {
        TaskStatus.READY,
        TaskStatus.RUNNING,
        TaskStatus.BLOCKED,
        TaskStatus.WAITING,
        TaskStatus.RETRYING,
        TaskStatus.PAUSED,
        TaskStatus.CANCELLED,
        TaskStatus.CANCELED,
        TaskStatus.FAILED,
        TaskStatus.TIMEOUT,
    },
    TaskStatus.READY: {
        TaskStatus.RUNNING,
        TaskStatus.BLOCKED,
        TaskStatus.WAITING,
        TaskStatus.RETRYING,
        TaskStatus.PAUSED,
        TaskStatus.CANCELLED,
        TaskStatus.CANCELED,
        TaskStatus.FAILED,
        TaskStatus.TIMEOUT,
    },
    TaskStatus.RUNNING: {
        TaskStatus.QUEUED,      # step_done 後重新排回 queue
        TaskStatus.READY,
        TaskStatus.RETRYING,
        TaskStatus.BLOCKED,
        TaskStatus.WAITING,
        TaskStatus.PAUSED,
        TaskStatus.FINISHED,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.CANCELED,
        TaskStatus.TIMEOUT,
    },
    TaskStatus.RETRYING: {
        TaskStatus.QUEUED,
        TaskStatus.READY,
        TaskStatus.RUNNING,
        TaskStatus.BLOCKED,
        TaskStatus.WAITING,
        TaskStatus.PAUSED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.CANCELED,
        TaskStatus.TIMEOUT,
    },
    TaskStatus.BLOCKED: {
        TaskStatus.QUEUED,
        TaskStatus.READY,
        TaskStatus.WAITING,
        TaskStatus.CANCELLED,
        TaskStatus.CANCELED,
        TaskStatus.FAILED,
        TaskStatus.TIMEOUT,
    },
    TaskStatus.WAITING: {
        TaskStatus.QUEUED,
        TaskStatus.READY,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.CANCELED,
        TaskStatus.FAILED,
        TaskStatus.TIMEOUT,
    },
    TaskStatus.PAUSED: {
        TaskStatus.QUEUED,
        TaskStatus.READY,
        TaskStatus.BLOCKED,
        TaskStatus.WAITING,
        TaskStatus.CANCELLED,
        TaskStatus.CANCELED,
        TaskStatus.FAILED,
    },
    TaskStatus.FINISHED: set(),
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
    TaskStatus.CANCELED: set(),
    TaskStatus.TIMEOUT: set(),
}


def normalize_status(status: Any, default: str = TaskStatus.QUEUED) -> str:
    text = str(status or "").strip().lower()
    if not text:
        return default

    if text == TaskStatus.COMPLETED:
        return TaskStatus.NORMALIZED_COMPLETED

    if text == TaskStatus.CANCELED:
        return TaskStatus.NORMALIZED_CANCELLED

    if text in TaskStatus.all_status():
        return text

    return default


def validate_status(status: str) -> bool:
    return normalize_status(status, default="") in TaskStatus.all_status()


def is_terminal(status: str) -> bool:
    return normalize_status(status) in {
        TaskStatus.FINISHED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.TIMEOUT,
    }


def is_ready_like(status: str) -> bool:
    return normalize_status(status) in READY_LIKE_STATES


def is_blocked_like(status: str) -> bool:
    return normalize_status(status) in BLOCKED_LIKE_STATES


def is_runnable(status: str) -> bool:
    return normalize_status(status) in RUNNABLE_STATES


def can_transition(from_status: str, to_status: str) -> bool:
    src = normalize_status(from_status)
    dst = normalize_status(to_status)

    if not src or not dst:
        return False

    if src == dst:
        return True

    allowed = VALID_TRANSITIONS.get(src, set())
    return dst in allowed


def require_transition(from_status: str, to_status: str) -> None:
    if not can_transition(from_status, to_status):
        src = normalize_status(from_status)
        dst = normalize_status(to_status)
        raise ValueError(f"invalid task state transition: {src} -> {dst}")


def transition_task(
    task: Dict[str, Any],
    to_status: str,
    *,
    append_history: bool = True,
    note: Optional[str] = None,
    allow_same: bool = True,
) -> Dict[str, Any]:
    """
    純 dict 轉移，不做 repo save。
    """
    if not isinstance(task, dict):
        raise TypeError("task must be dict")

    src = normalize_status(task.get("status"))
    dst = normalize_status(to_status)

    if src == dst and allow_same:
        updated = dict(task)
        updated["status"] = dst
        if append_history:
            _append_history(updated, dst, note=note, dedupe=True)
        return updated

    require_transition(src, dst)

    updated = dict(task)
    updated["status"] = dst

    if append_history:
        _append_history(updated, dst, note=note, dedupe=False)

    return updated


def transition_result(
    task: Dict[str, Any],
    to_status: str,
    *,
    append_history: bool = True,
    note: Optional[str] = None,
    allow_same: bool = True,
) -> Dict[str, Any]:
    old_status = normalize_status(task.get("status"))
    updated = transition_task(
        task,
        to_status,
        append_history=append_history,
        note=note,
        allow_same=allow_same,
    )
    new_status = normalize_status(updated.get("status"))

    return {
        "ok": True,
        "old_status": old_status,
        "new_status": new_status,
        "task": updated,
    }


def next_status_for_dependency(
    current_status: str,
    *,
    dependencies_ready: bool,
) -> str:
    current = normalize_status(current_status)

    if is_terminal(current):
        return current

    if dependencies_ready:
        if current in {
            TaskStatus.BLOCKED,
            TaskStatus.WAITING,
            TaskStatus.QUEUED,
            TaskStatus.READY,
        }:
            return TaskStatus.READY
        return current

    if current in {
        TaskStatus.QUEUED,
        TaskStatus.READY,
        TaskStatus.BLOCKED,
        TaskStatus.WAITING,
    }:
        return TaskStatus.BLOCKED

    return current


def next_status_for_runner_result(
    current_status: str,
    runner_result: Dict[str, Any],
) -> str:
    current = normalize_status(current_status)

    if not isinstance(runner_result, dict):
        return TaskStatus.FAILED

    explicit_status = runner_result.get("status")
    action = str(runner_result.get("action", "") or "").strip().lower()
    ok = bool(runner_result.get("ok", False))

    if explicit_status:
        return normalize_status(explicit_status)

    if action in {"task_finished", "finished"}:
        return TaskStatus.FINISHED

    if action in {"task_timeout"}:
        return TaskStatus.TIMEOUT

    if action in {"task_cancelled"}:
        return TaskStatus.CANCELLED

    if action in {"task_blocked"}:
        return TaskStatus.BLOCKED

    if action in {"step_failed", "exception_failed"}:
        return TaskStatus.FAILED

    if action in {"step_completed"}:
        return TaskStatus.QUEUED

    if ok:
        return current

    return TaskStatus.FAILED


def _append_history(
    task: Dict[str, Any],
    status: str,
    *,
    note: Optional[str] = None,
    dedupe: bool = False,
) -> None:
    history = task.get("history", [])

    if isinstance(history, str):
        history = [p.strip() for p in history.split("->") if p.strip()]
    elif not isinstance(history, list):
        history = []

    label = status if not note else f"{status} ({note})"

    if dedupe and history and history[-1] == label:
        task["history"] = history
        return

    history.append(label)
    task["history"] = history