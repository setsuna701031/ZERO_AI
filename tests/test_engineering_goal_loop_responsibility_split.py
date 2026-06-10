from pathlib import Path


def test_engineering_goal_loop_uses_coordinators() -> None:
    source = Path("core/tasks/engineering_goal_loop.py").read_text(encoding="utf-8")
    assert "AdaptiveLoopCoordinator" in source
    assert "LifecycleCoordinator" in source
    assert "GoalLoopCoordinator" in source
    assert "goal_loop_uses_adaptive_loop_coordinator" in source
    assert "goal_loop_uses_lifecycle_coordinator" in source
    assert "goal_loop_uses_goal_loop_coordinator" in source


def test_engineering_goal_loop_no_longer_builds_adaptive_loop_inline() -> None:
    source = Path("core/tasks/engineering_goal_loop.py").read_text(encoding="utf-8")
    assert "build_adaptive_replan_contract(" not in source
    assert "build_adaptive_observation_from_cycle(" not in source
    assert "build_adaptive_delta(" not in source
    assert "build_adaptive_loop_contract(" not in source
