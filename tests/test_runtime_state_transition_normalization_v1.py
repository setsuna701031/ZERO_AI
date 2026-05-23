from core.runtime.runtime_state_normalizer import (
    normalize_runtime_transition,
)


def test_runtime_transition_normalization():
    result = normalize_runtime_transition(
        "blocked",
        "restored",
    )

    assert result["from_state"] == "SESSION_BLOCKED"
    assert result["to_state"] == "SESSION_RESTORED"