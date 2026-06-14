from core.program.program_coordinator import ProgramCoordinator
from core.evidence import EvidenceRecord, EvidenceValidator
from core.goals.goal_completion_authority import GoalCompletionAuthority


def _attestation():
    evidence = EvidenceValidator().validate(EvidenceRecord("e1", "goal-1", None, "test", "ok", "now"))
    return GoalCompletionAuthority().complete_goal(goal_id="goal-1", evidence_refs=[evidence], all_subgoals_completed=True)


def test_program_completes_only_when_all_sessions_done_or_archived() -> None:
    coordinator = ProgramCoordinator()
    unattested = coordinator.aggregate_sessions([
        {"session_state": "completed"},
        {"session_state": "archived"},
    ])
    summary = coordinator.aggregate_sessions(
        [
            {"session_state": "completed"},
            {"session_state": "archived"},
        ],
        goal_id="goal-1",
        completion_attestation=_attestation(),
    )

    assert unattested["program_state"] == "active"
    assert unattested["terminal"] is False
    assert summary["program_state"] == "completed"
    assert summary["terminal"] is True


def test_program_stays_active_when_any_session_active() -> None:
    coordinator = ProgramCoordinator()
    summary = coordinator.aggregate_sessions([
        {"session_state": "completed"},
        {"session_state": "waiting_user"},
    ])

    assert summary["program_state"] == "active"
    assert summary["terminal"] is False
