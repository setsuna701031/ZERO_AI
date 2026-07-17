from core.adaptive import AdaptiveDecisionType


def test_adaptive_decision_types_are_bounded() -> None:
    assert {item.value for item in AdaptiveDecisionType} == {
        "continue_active",
        "resume_blocked",
        "request_evidence",
        "mark_blocked",
        "wait_for_user",
        "no_action",
    }
