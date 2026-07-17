from __future__ import annotations

from pathlib import Path

from core.adaptive.continuation_runtime import ContinuationRuntime
from core.adaptive.replan_runtime import ReplanRuntime
from core.session.engineering_session_runtime import EngineeringSessionRuntime
from core.tasks.goal_loop_terminal_coordinator import GoalLoopTerminalCoordinator


def test_runtime_single_source_of_truth_owner_matrix() -> None:
    owner_matrix = {
        "current_goal_id": "ContinuationRuntime",
        "continuation_count": "ContinuationRuntime",
        "replan_count": "ReplanRuntime",
    }

    assert owner_matrix["current_goal_id"] == "ContinuationRuntime"
    assert owner_matrix["continuation_count"] == "ContinuationRuntime"
    assert owner_matrix["replan_count"] == "ReplanRuntime"
    assert "EngineeringSessionRuntime" not in set(owner_matrix.values())


def test_terminal_coordinator_reports_runtime_state_without_repairing_drift(tmp_path: Path) -> None:
    session_runtime = EngineeringSessionRuntime.start("goal_a", max_cycles=2, max_replans=2, max_continuations=2).replace(
        current_goal_id="goal_a",
        continuation_count=2,
        replan_count=2,
    )
    continuation_runtime = ContinuationRuntime.start("goal_a__continuation_1", continuation_count=1, max_continuations=2)
    replan_runtime = ReplanRuntime.start(replan_count=1, max_replans=2)
    terminal = GoalLoopTerminalCoordinator(repo_root=tmp_path)

    result = terminal.build_result(
        target_goal_id="goal_a",
        current_goal_id=session_runtime.current_goal_id,
        terminal=True,
        stop_reason="stop",
        cycles=[{"goal_id": "goal_a", "adaptive_decision_record": {"decision": "blocked"}}],
        session_runtime=session_runtime,
        continuation_runtime=continuation_runtime,
        replan_runtime=replan_runtime,
        max_cycles=2,
        max_replans=2,
        max_continuations=2,
    )

    assert result["engineering_session_runtime"]["continuation_count"] == 2
    assert result["continuation_runtime"]["continuation_count"] == 1
    assert result["engineering_session_runtime"]["replan_count"] == 2
    assert result["replan_runtime"]["replan_count"] == 1
    assert result["goal_loop_terminal_coordinator"]["built_terminal_result"] is True
