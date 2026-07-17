from core.program.program_coordinator import ProgramCoordinator


def test_failed_session_makes_program_failed() -> None:
    coordinator = ProgramCoordinator()
    updated = coordinator.attach_program_from_sessions(
        {"cycle_index": 0, "goal_id": "g1"},
        session_states=[{"session_state": "completed"}, {"session_state": "failed"}],
        from_state="active",
    )

    assert updated["engineering_program_state"]["accepted"] is True
    assert updated["engineering_program_state"]["program_state"] == "failed"


def test_archived_program_cannot_resume_to_active() -> None:
    coordinator = ProgramCoordinator()
    updated = coordinator.attach_program_from_sessions(
        {"cycle_index": 0, "goal_id": "g1"},
        session_states=[{"session_state": "active"}],
        from_state="completed",
    )

    assert updated["engineering_program_state"]["accepted"] is False
    assert updated["engineering_program_state"]["blocked_reason"] == "illegal_transition:completed->active"
