from __future__ import annotations

from core.runtime.runtime_state_names import (
    SESSION_BLOCKED,
    SESSION_FAILED,
    SESSION_RESTORED,
    SESSION_ROLLED_BACK,
    SESSION_RUNNING,
    SESSION_SEALED,
)

_RUNTIME_STATE_ALIASES = {
    "running": SESSION_RUNNING,
    "active": SESSION_RUNNING,
    "blocked": SESSION_BLOCKED,
    "locked": SESSION_BLOCKED,
    "sealed": SESSION_SEALED,
    "failed": SESSION_FAILED,
    "rollback_required": SESSION_ROLLED_BACK,
    "rolled_back": SESSION_ROLLED_BACK,
    "restored": SESSION_RESTORED,
}


def normalize_runtime_state(state: str | None) -> str:
    if not state:
        return SESSION_RUNNING

    normalized = _RUNTIME_STATE_ALIASES.get(
        str(state).strip().lower()
    )

    if normalized:
        return normalized

    return str(state)


def normalize_runtime_transition(
    from_state: str | None,
    to_state: str | None,
) -> dict:
    return {
        "from_state": normalize_runtime_state(from_state),
        "to_state": normalize_runtime_state(to_state),
    }