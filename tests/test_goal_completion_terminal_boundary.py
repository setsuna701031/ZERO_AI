from __future__ import annotations

from pathlib import Path

from core.tasks.goal_loop_terminal_coordinator import GoalLoopTerminalCoordinator


def test_terminal_coordinator_does_not_complete_goal_or_persist(tmp_path: Path) -> None:
    terminal = GoalLoopTerminalCoordinator(repo_root=tmp_path)
    result = terminal.build_result(
        target_goal_id="goal_a",
        current_goal_id="goal_a",
        terminal=True,
        stop_reason="stop",
        cycles=[{"goal_id": "goal_a", "adaptive_decision_record": {"decision": "complete"}}],
    )

    marker = result["goal_loop_terminal_coordinator"]
    assert marker["built_terminal_result"] is True
    assert marker["execution_path"]["terminal_assembly_only"] is True
    assert marker["execution_path"]["persists_records"] is False
    assert marker["execution_path"]["writes_evidence"] is False
    assert marker["execution_path"]["mutates_runtime"] is False
    assert "goal_state" not in result
