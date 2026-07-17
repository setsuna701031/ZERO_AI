from core.adaptive.adaptive_replan_transition import AdaptiveReplanTransition
from core.adaptive.adaptive_replan_validator import AdaptiveReplanValidator
from core.evidence import EvidenceRecord, EvidenceValidator
from core.goals.goal_completion_authority import GoalCompletionAuthority


def test_validator_accepts_known_transitions() -> None:
    validator = AdaptiveReplanValidator()
    for target in ("continue", "replan", "blocked", "wait_for_user", "refuse", "stop"):
        result = validator.validate(AdaptiveReplanTransition("continue", target, target))
        assert result.accepted is True


def test_validator_requires_completion_authority_for_complete_transition() -> None:
    evidence = EvidenceValidator().validate(EvidenceRecord("e1", "goal-a", None, "test", "ok", "now"))
    attestation = GoalCompletionAuthority().complete_goal(
        goal_id="goal-a",
        evidence_refs=[evidence],
        all_subgoals_completed=True,
    )

    rejected = AdaptiveReplanValidator().validate(
        AdaptiveReplanTransition("continue", "complete", "complete")
    )
    accepted = AdaptiveReplanValidator().validate(
        AdaptiveReplanTransition(
            "continue",
            "complete",
            "complete",
            goal_id="goal-a",
            completion_attestation=attestation,
        )
    )

    assert rejected.accepted is False
    assert rejected.blocked_reason == "canonical_completion_attestation_required"
    assert accepted.accepted is True


def test_validator_rejects_terminal_back_to_continue() -> None:
    result = AdaptiveReplanValidator().validate(AdaptiveReplanTransition("complete", "continue", "continue"))
    assert result.accepted is False
    assert "illegal_transition" in result.blocked_reason
