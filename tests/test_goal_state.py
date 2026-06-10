from core.goals import GoalState, SubgoalState, TransitionAction


def test_goal_state_contract_values_are_sealed() -> None:
    assert [state.value for state in GoalState] == [
        "created", "planned", "active", "blocked", "resumable", "completed", "failed"
    ]
    assert [state.value for state in SubgoalState] == [
        "pending", "active", "blocked", "resumable", "completed", "failed"
    ]
    assert TransitionAction.RESUME_READY.value == "resume_ready"
