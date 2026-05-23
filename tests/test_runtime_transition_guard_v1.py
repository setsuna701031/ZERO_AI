import pytest

from core.runtime.runtime_state_names import (
    SESSION_BLOCKED,
    SESSION_RUNNING,
    SESSION_SEALED,
)

from core.runtime.runtime_transition_enforcer import (
    RuntimeTransitionRejected,
)

from core.runtime.runtime_transition_guard import (
    guard_runtime_transition,
)


def test_runtime_transition_guard_accepts_valid_transition():
    result = guard_runtime_transition(
        SESSION_RUNNING,
        SESSION_BLOCKED,
    )

    assert result["ok"] is True
    assert result["transition_guarded"] is True


def test_runtime_transition_guard_rejects_invalid_transition():
    with pytest.raises(RuntimeTransitionRejected):
        guard_runtime_transition(
            SESSION_SEALED,
            SESSION_RUNNING,
        )