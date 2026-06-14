from core.program.engineering_program_state_machine import EngineeringProgramStateMachine
from core.evidence import EvidenceRecord, EvidenceValidator
from core.goals.goal_completion_authority import GoalCompletionAuthority


def _attestation():
    evidence = EvidenceValidator().validate(EvidenceRecord("e1", "goal-1", None, "test", "ok", "now"))
    return GoalCompletionAuthority().complete_goal(goal_id="goal-1", evidence_refs=[evidence], all_subgoals_completed=True)


def test_engineering_program_state_machine_maps_session_completed() -> None:
    result = EngineeringProgramStateMachine().evaluate_session(
        {"session_state": "completed", "accepted": True, "reason": "done"},
        from_state="active",
        goal_id="goal-1",
        completion_attestation=_attestation(),
    )
    assert result.accepted is True
    assert result.program_state == "completed"
    assert result.terminal is True


def test_engineering_program_state_machine_failed_cannot_reactivate() -> None:
    result = EngineeringProgramStateMachine().evaluate_session(
        {"session_state": "active", "accepted": True},
        from_state="failed",
    )
    assert result.accepted is False
