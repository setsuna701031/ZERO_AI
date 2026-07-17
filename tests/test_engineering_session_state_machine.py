from core.session.engineering_session_state_machine import EngineeringSessionStateMachine
from core.evidence import EvidenceRecord, EvidenceValidator
from core.goals.goal_completion_authority import GoalCompletionAuthority


def _attestation():
    evidence = EvidenceValidator().validate(EvidenceRecord("e1", "goal-1", None, "test", "ok", "now"))
    return GoalCompletionAuthority().complete_goal(goal_id="goal-1", evidence_refs=[evidence], all_subgoals_completed=True)


def test_session_state_machine_maps_lifecycle():
    machine = EngineeringSessionStateMachine()
    assert machine.evaluate_lifecycle({"lifecycle_state": "continuing", "task_id": "goal-1"}, from_state="created").session_state == "active"
    assert machine.evaluate_lifecycle({"lifecycle_state": "waiting_evidence", "task_id": "goal-1"}, from_state="active").session_state == "waiting_user"
    rejected = machine.evaluate_lifecycle({"lifecycle_state": "completed", "task_id": "goal-1"}, from_state="active")
    assert rejected.accepted is False
    completed = machine.evaluate_lifecycle(
        {"lifecycle_state": "completed", "task_id": "goal-1"},
        from_state="active",
        completion_attestation=_attestation(),
    )
    assert completed.terminal is True


def test_session_state_machine_blocks_completed_to_active():
    machine = EngineeringSessionStateMachine()
    result = machine.evaluate_lifecycle({"lifecycle_state": "running", "task_id": "task-1"}, from_state="completed")
    assert result.accepted is False
