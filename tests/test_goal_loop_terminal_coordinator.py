from core.tasks.goal_loop_terminal_coordinator import GoalLoopTerminalCoordinator


class Runtime:
    def __init__(self, payload):
        self.payload = payload
    def to_dict(self):
        return dict(self.payload)


def test_terminal_coordinator_builds_result(tmp_path) -> None:
    coordinator = GoalLoopTerminalCoordinator(repo_root=tmp_path, evidence_chain_summary=lambda goal_id: {"goal_id": goal_id})
    result = coordinator.build_result(
        target_goal_id="goal_a",
        current_goal_id="goal_a",
        terminal=True,
        stop_reason="complete",
        cycles=[{"adaptive_decision_record": {"decision": "complete"}}],
        max_cycles=1,
        max_replans=1,
        max_continuations=1,
        session_runtime=Runtime({"current_goal_id": "goal_a"}),
        continuation_runtime=Runtime({"continuation_count": 0}),
        replan_runtime=Runtime({"replan_count": 0}),
    )
    assert result["ok"] is True
    assert result["goal_loop_terminal_coordinator"]["built_terminal_result"] is True
    assert result["execution_path"]["goal_loop_uses_terminal_coordinator"] is True
