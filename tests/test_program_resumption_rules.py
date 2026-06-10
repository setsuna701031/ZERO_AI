from core.program.program_coordinator import ProgramCoordinator


def test_blocked_program_can_resume_when_sessions_are_active() -> None:
    coordinator = ProgramCoordinator()
    updated = coordinator.attach_program_from_sessions(
        {"cycle_index": 1, "goal_id": "g1"},
        session_states=[{"session_state": "active"}, {"session_state": "completed"}],
        from_state="blocked",
    )

    assert updated["engineering_program_state"]["accepted"] is True
    assert updated["engineering_program_state"]["program_state"] == "active"
    assert updated["program_coordinator"]["multi_session_aggregation"] is True
