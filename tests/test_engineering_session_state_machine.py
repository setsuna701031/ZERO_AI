from core.session.engineering_session_state_machine import EngineeringSessionStateMachine


def test_session_state_machine_maps_lifecycle():
    machine = EngineeringSessionStateMachine()
    assert machine.evaluate_lifecycle({"lifecycle_state": "continuing", "task_id": "task-1"}, from_state="created").session_state == "active"
    assert machine.evaluate_lifecycle({"lifecycle_state": "waiting_evidence", "task_id": "task-1"}, from_state="active").session_state == "waiting_user"
    assert machine.evaluate_lifecycle({"lifecycle_state": "completed", "task_id": "task-1"}, from_state="active").terminal is True


def test_session_state_machine_blocks_completed_to_active():
    machine = EngineeringSessionStateMachine()
    result = machine.evaluate_lifecycle({"lifecycle_state": "running", "task_id": "task-1"}, from_state="completed")
    assert result.accepted is False
