from __future__ import annotations

from typing import Any, Dict, Optional, Set


READY_STATUS_ALIASES = {
    "queued",
    "ready",
    "retry",
    "retrying",
}

BLOCKED_STATUS_ALIASES = {
    "blocked",
    "waiting",
}

NON_RUNNABLE_STATUS_ALIASES = {
    "created",
    "planning",
    "replanning",
    "running",
    "paused",
}


def normalize_queue_status(value: Any) -> str:
    return str(value or "").strip().lower()


def is_terminal_queue_status(status: Any, terminal_statuses: Set[str]) -> bool:
    terminal_set = {normalize_queue_status(item) for item in terminal_statuses or set()}
    return normalize_queue_status(status) in terminal_set


def is_blocked_queue_status(
    status: Any,
    *,
    status_blocked: str = "blocked",
    blocked_reason: Any = "",
) -> bool:
    blocked_set = {normalize_queue_status(item) for item in BLOCKED_STATUS_ALIASES}
    if status_blocked:
        blocked_set.add(normalize_queue_status(status_blocked))
    return (
        normalize_queue_status(status) in blocked_set
        or bool(str(blocked_reason or "").strip())
    )


def is_dispatchable_queue_status(status: Any, ready_statuses: Set[str]) -> bool:
    effective_ready_statuses = {
        normalize_queue_status(item)
        for item in (set(ready_statuses or set()) | READY_STATUS_ALIASES)
    }
    effective_ready_statuses.discard("created")
    return normalize_queue_status(status) in effective_ready_statuses


def decide_queue_transition(
    *,
    status: Any,
    terminal_statuses: Set[str],
    ready_statuses: Set[str],
    status_blocked: str = "blocked",
    deps_ready: bool = True,
    blocked_reason: Any = "",
    running_task: Optional[Any] = None,
    already_queued: bool = False,
    overwrite: bool = False,
) -> Dict[str, Any]:
    normalized_status = normalize_queue_status(status)

    if running_task is not None:
        return {"action": "remove", "reason": "running_task", "dispatchable": False}

    if is_terminal_queue_status(normalized_status, terminal_statuses):
        return {"action": "remove", "reason": "terminal", "dispatchable": False}

    if normalized_status in NON_RUNNABLE_STATUS_ALIASES:
        return {"action": "remove", "reason": "non_runnable", "dispatchable": False}

    if not deps_ready:
        return {
            "action": "block",
            "reason": str(blocked_reason or "dependency_not_ready"),
            "dispatchable": False,
        }

    if is_blocked_queue_status(
        normalized_status,
        status_blocked=status_blocked,
        blocked_reason=blocked_reason,
    ):
        return {"action": "unblock", "reason": "blocked_ready", "dispatchable": False}

    if not is_dispatchable_queue_status(normalized_status, ready_statuses):
        return {"action": "remove", "reason": "not_ready", "dispatchable": False}

    if already_queued and not overwrite:
        return {"action": "keep", "reason": "already_queued", "dispatchable": True}

    return {"action": "enqueue", "reason": "ready", "dispatchable": True}
