from core.runtime.runtime_state_names import (

    SESSION_BLOCKED,
    SESSION_FAILED,
    SESSION_RESTORED,
    SESSION_ROLLED_BACK,
    SESSION_RUNNING,
    SESSION_SEALED,
)

from core.runtime.runtime_transition_contract import (
    is_runtime_transition_allowed,
    validate_runtime_transition,
)
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



def test_running_to_blocked_allowed():
    assert (
        is_runtime_transition_allowed(
            SESSION_RUNNING,
            SESSION_BLOCKED,
        )
        is True
    )


def test_blocked_to_sealed_allowed():
    assert (
        is_runtime_transition_allowed(
            SESSION_BLOCKED,
            SESSION_SEALED,
        )
        is True
    )


def test_sealed_to_running_denied():
    assert (
        is_runtime_transition_allowed(
            SESSION_SEALED,
            SESSION_RUNNING,
        )
        is False
    )


def test_restored_to_running_allowed():
    assert (
        is_runtime_transition_allowed(
            SESSION_RESTORED,
            SESSION_RUNNING,
        )
        is True
    )


def test_failed_to_restored_denied():
    assert (
        is_runtime_transition_allowed(
            SESSION_FAILED,
            SESSION_RESTORED,
        )
        is False
    )


def test_runtime_transition_validation():
    result = validate_runtime_transition(
        SESSION_BLOCKED,
        SESSION_RESTORED,
    )

    assert result["allowed"] is True