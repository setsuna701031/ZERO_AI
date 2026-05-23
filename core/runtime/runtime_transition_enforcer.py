from __future__ import annotations

from core.runtime.runtime_transition_contract import (
    is_runtime_transition_allowed,
)


class RuntimeTransitionRejected(RuntimeError):
    pass


def enforce_runtime_transition(
    from_state: str,
    to_state: str,
) -> dict:
    allowed = is_runtime_transition_allowed(
        from_state,
        to_state,
    )

    if not allowed:
        raise RuntimeTransitionRejected(
            f"runtime transition denied: "
            f"{from_state} -> {to_state}"
        )

    return {
        "ok": True,
        "from_state": from_state,
        "to_state": to_state,
        "transition_allowed": True,
    }