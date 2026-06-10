from core.program.engineering_program_state_machine import EngineeringProgramStateMachine


def test_engineering_program_state_machine_maps_session_completed() -> None:
    result = EngineeringProgramStateMachine().evaluate_session(
        {"session_state": "completed", "accepted": True, "reason": "done"},
        from_state="active",
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
