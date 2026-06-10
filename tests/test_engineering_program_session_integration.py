from core.program.program_coordinator import ProgramCoordinator


def test_program_coordinator_attaches_program_state_from_session() -> None:
    cycle = {
        "goal_id": "goal-1",
        "engineering_session_state": {
            "session_state": "active",
            "accepted": True,
            "reason": "session_active",
        },
    }
    updated = ProgramCoordinator().attach_program(cycle, from_state="created")
    assert updated["engineering_program_state"]["program_state"] == "active"
    assert updated["program_coordinator"]["attached_engineering_program_state"] is True
    assert updated["program_coordinator"]["execution_path"]["mutates_memory"] is False
