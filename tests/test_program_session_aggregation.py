from core.program.program_coordinator import ProgramCoordinator


def test_program_completes_only_when_all_sessions_done_or_archived() -> None:
    coordinator = ProgramCoordinator()
    summary = coordinator.aggregate_sessions([
        {"session_state": "completed"},
        {"session_state": "archived"},
    ])

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
