from core.session.engineering_session_transition import EngineeringSessionTransition


def test_engineering_session_transition_to_dict():
    transition = EngineeringSessionTransition(
        "created",
        "active",
        "active",
        "start",
        {"lifecycle_state": "continuing"},
        {"goal_id": "goal-1"},
    )
    data = transition.to_dict()
    assert data["from_state"] == "created"
    assert data["to_state"] == "active"
    assert data["lifecycle_state"]["lifecycle_state"] == "continuing"
    assert data["cycle"]["goal_id"] == "goal-1"
    assert data["execution_path"]["mutates_memory"] is False
