from core.program.program_coordinator import ProgramCoordinator


def test_program_blocks_when_any_session_blocked() -> None:
    coordinator = ProgramCoordinator()
    summary = coordinator.aggregate_sessions([
        {"session_state": "completed"},
        {"session_state": "active"},
        {"session_state": "blocked"},
    ])

    assert summary["program_state"] == "blocked"
    assert summary["session_state_counts"]["blocked"] == 1
    assert summary["session_state_counts"]["active"] == 1
    assert summary["session_state_counts"]["completed"] == 1
