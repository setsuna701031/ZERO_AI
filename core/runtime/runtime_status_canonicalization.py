from __future__ import annotations

from typing import Any

RUNTIME_STATUS_PENDING = "pending"
RUNTIME_STATUS_RUNNING = "running"
RUNTIME_STATUS_COMPLETED = "completed"
RUNTIME_STATUS_FAILED = "failed"
RUNTIME_STATUS_BLOCKED = "blocked"
RUNTIME_STATUS_CANCELLED = "cancelled"
RUNTIME_STATUS_UNKNOWN = "unknown"

COMPLETED_STATUS_ALIASES = {
    "complete",
    "completed",
    "done",
    "finished",
    "success",
    "succeeded",
    "ok",
    "passed",
    "finalized",
}

FAILED_STATUS_ALIASES = {
    "fail",
    "failed",
    "failure",
    "error",
    "errored",
    "exception",
    "rejected",
}

BLOCKED_STATUS_ALIASES = {
    "blocked",
    "waiting",
    "paused",
    "deferred",
    "stalled",
}

RUNNING_STATUS_ALIASES = {
    "running",
    "active",
    "executing",
    "in_progress",
    "in-progress",
    "started",
    "working",
}

PENDING_STATUS_ALIASES = {
    "pending",
    "queued",
    "created",
    "planned",
    "ready",
    "new",
}

CANCELLED_STATUS_ALIASES = {
    "cancelled",
    "canceled",
    "aborted",
    "stopped",
}

TERMINAL_RUNTIME_STATUSES = {
    RUNTIME_STATUS_COMPLETED,
    RUNTIME_STATUS_FAILED,
    RUNTIME_STATUS_BLOCKED,
    RUNTIME_STATUS_CANCELLED,
}

ACTIVE_RUNTIME_STATUSES = {
    RUNTIME_STATUS_PENDING,
    RUNTIME_STATUS_RUNNING,
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def canonical_runtime_status(value: Any, *, default: str = RUNTIME_STATUS_UNKNOWN) -> str:
    status = _text(value)

    if not status:
        return default

    if status in COMPLETED_STATUS_ALIASES:
        return RUNTIME_STATUS_COMPLETED

    if status in FAILED_STATUS_ALIASES:
        return RUNTIME_STATUS_FAILED

    if status in BLOCKED_STATUS_ALIASES:
        return RUNTIME_STATUS_BLOCKED

    if status in RUNNING_STATUS_ALIASES:
        return RUNTIME_STATUS_RUNNING

    if status in PENDING_STATUS_ALIASES:
        return RUNTIME_STATUS_PENDING

    if status in CANCELLED_STATUS_ALIASES:
        return RUNTIME_STATUS_CANCELLED

    return status


def canonical_runtime_state(value: Any, *, default: str = RUNTIME_STATUS_UNKNOWN) -> str:
    return canonical_runtime_status(value, default=default)


def is_runtime_completed(value: Any) -> bool:
    return canonical_runtime_status(value) == RUNTIME_STATUS_COMPLETED


def is_runtime_failed(value: Any) -> bool:
    return canonical_runtime_status(value) == RUNTIME_STATUS_FAILED


def is_runtime_blocked(value: Any) -> bool:
    return canonical_runtime_status(value) == RUNTIME_STATUS_BLOCKED


def is_runtime_cancelled(value: Any) -> bool:
    return canonical_runtime_status(value) == RUNTIME_STATUS_CANCELLED


def is_runtime_terminal(value: Any) -> bool:
    return canonical_runtime_status(value) in TERMINAL_RUNTIME_STATUSES


def is_runtime_active(value: Any) -> bool:
    return canonical_runtime_status(value) in ACTIVE_RUNTIME_STATUSES


def canonicalize_runtime_payload_status(
    payload: dict[str, Any],
    *,
    status_key: str = "status",
    default: str = RUNTIME_STATUS_UNKNOWN,
) -> dict[str, Any]:
    updated = dict(payload)
    updated[status_key] = canonical_runtime_status(updated.get(status_key), default=default)
    return updated