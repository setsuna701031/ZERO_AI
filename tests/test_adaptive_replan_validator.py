from core.adaptive.adaptive_replan_transition import AdaptiveReplanTransition
from core.adaptive.adaptive_replan_validator import AdaptiveReplanValidator


def test_validator_accepts_known_transitions() -> None:
    validator = AdaptiveReplanValidator()
    for target in ("continue", "replan", "blocked", "complete", "wait_for_user", "refuse", "stop"):
        result = validator.validate(AdaptiveReplanTransition("continue", target, target))
        assert result.accepted is True


def test_validator_rejects_terminal_back_to_continue() -> None:
    result = AdaptiveReplanValidator().validate(AdaptiveReplanTransition("complete", "continue", "continue"))
    assert result.accepted is False
    assert "illegal_transition" in result.blocked_reason
