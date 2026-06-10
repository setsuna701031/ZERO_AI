from core.session.session_coordinator import SessionCoordinator


def test_session_coordinator_attaches_session_state():
    cycle = {
        "goal_id": "goal-1",
        "engineering_lifecycle_state": {
            "lifecycle_state": "continuing",
            "reason": "continue_next_cycle",
        },
    }
    updated = SessionCoordinator().attach_session(cycle, from_state="created")
    assert updated["engineering_session_state"]["session_state"] == "active"
    assert updated["session_coordinator"]["attached_engineering_session_state"] is True
    assert updated["session_coordinator"]["execution_path"]["mutates_memory"] is False
