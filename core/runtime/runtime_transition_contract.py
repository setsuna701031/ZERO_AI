from __future__ import annotations

from core.runtime.runtime_state_names import (
    SESSION_BLOCKED,
    SESSION_FAILED,
    SESSION_RESTORED,
    SESSION_ROLLED_BACK,
    SESSION_RUNNING,
    SESSION_SEALED,
)

_ALLOWED_RUNTIME_TRANSITIONS = {
    SESSION_RUNNING: {
        SESSION_BLOCKED,
        SESSION_FAILED,
    },
    SESSION_BLOCKED: {
        SESSION_SEALED,
        SESSION_ROLLED_BACK,
        SESSION_RESTORED,
    },
    SESSION_SEALED: {
        SESSION_RESTORED,
    },
    SESSION_RESTORED: {
        SESSION_RUNNING,
    },
    SESSION_ROLLED_BACK: {
        SESSION_RESTORED,
    },
    SESSION_FAILED: {
        SESSION_ROLLED_BACK,
    },
}


def is_runtime_transition_allowed(
    from_state: str,
    to_state: str,
) -> bool:
    allowed_targets = _ALLOWED_RUNTIME_TRANSITIONS.get(
        from_state,
        set(),
    )

    return to_state in allowed_targets


def validate_runtime_transition(
    from_state: str,
    to_state: str,
) -> dict:
    allowed = is_runtime_transition_allowed(
        from_state,
        to_state,
    )

    return {
        "allowed": allowed,
        "from_state": from_state,
        "to_state": to_state,
    }