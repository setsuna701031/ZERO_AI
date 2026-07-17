from core.runtime.runtime_state_normalizer import (
    normalize_runtime_state,
)


def test_blocked_state_normalization():
    assert (
        normalize_runtime_state("blocked")
        == "SESSION_BLOCKED"
    )


def test_locked_state_normalization():
    assert (
        normalize_runtime_state("locked")
        == "SESSION_BLOCKED"
    )


def test_sealed_state_normalization():
    assert (
        normalize_runtime_state("sealed")
        == "SESSION_SEALED"
    )


def test_rollback_state_normalization():
    assert (
        normalize_runtime_state("rollback_required")
        == "SESSION_ROLLED_BACK"
    )


def test_restored_state_normalization():
    assert (
        normalize_runtime_state("restored")
        == "SESSION_RESTORED"
    )