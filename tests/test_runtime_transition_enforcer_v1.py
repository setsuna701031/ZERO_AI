import pytest

from core.runtime.runtime_state_names import (
    SESSION_BLOCKED,
    SESSION_FAILED,
    SESSION_RESTORED,
    SESSION_RUNNING,
    SESSION_SEALED,
)

from core.runtime.runtime_transition_enforcer import (
    RuntimeTransitionRejected,
    enforce_runtime_transition,
)


def test_runtime_transition_enforcement_accepts_valid_transition():
    result = enforce_runtime_transition(
        SESSION_RUNNING,
        SESSION_BLOCKED,
    )

    assert result["ok"] is True
    assert result["transition_allowed"] is True


def test_runtime_transition_enforcement_rejects_invalid_transition():
    with pytest.raises(RuntimeTransitionRejected):
        enforce_runtime_transition(
            SESSION_SEALED,
            SESSION_RUNNING,
        )


def test_runtime_transition_enforcement_rejects_failed_restore():
    with pytest.raises(RuntimeTransitionRejected):
        enforce_runtime_transition(
            SESSION_FAILED,
            SESSION_RESTORED,
        )