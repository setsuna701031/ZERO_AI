import inspect

from core.tasks.engineering_goal_loop import EngineeringGoalLoop


def test_goal_loop_accepts_session_progression_coordinator_injection() -> None:
    signature = inspect.signature(EngineeringGoalLoop.__init__)

    assert "session_progression_coordinator" in signature.parameters


def test_goal_loop_uses_session_progression_boundary() -> None:
    source = inspect.getsource(EngineeringGoalLoop.run_until_terminal)

    assert "session_progression_coordinator.start_runtime" in source
    assert "session_progression_coordinator.attach_cycle_progression" in source
    assert "goal_loop_uses_session_progression_coordinator" in source
