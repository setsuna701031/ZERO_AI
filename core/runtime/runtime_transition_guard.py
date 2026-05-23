from __future__ import annotations

from core.runtime.runtime_transition_enforcer import (
    enforce_runtime_transition,
)


def guard_runtime_transition(
    from_state: str,
    to_state: str,
    *,
    metadata: dict | None = None,
) -> dict:
    result = enforce_runtime_transition(
        from_state,
        to_state,
    )

    return {
        "ok": True,
        "from_state": from_state,
        "to_state": to_state,
        "transition_guarded": True,
        "metadata": dict(metadata or {}),
        "enforcement": result,
    }