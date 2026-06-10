from core.adaptive.adaptive_replan_state import AdaptiveReplanState, clean_adaptive_replan_state


def test_clean_adaptive_replan_state_accepts_canonical_and_aliases() -> None:
    assert clean_adaptive_replan_state(AdaptiveReplanState.CONTINUE) == "continue"
    assert clean_adaptive_replan_state("completed") == "complete"
    assert clean_adaptive_replan_state("request_replan") == "replan"
    assert clean_adaptive_replan_state("request_user_review") == "wait_for_user"


def test_clean_adaptive_replan_state_rejects_unknown() -> None:
    try:
        clean_adaptive_replan_state("teleport")
    except ValueError as exc:
        assert "adaptive_replan_requires_valid_state" in str(exc)
    else:
        raise AssertionError("unknown state should be rejected")
