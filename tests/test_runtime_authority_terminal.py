from core.tasks.goal_loop_terminal_coordinator import GoalLoopTerminalCoordinator
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




class Runtime:
    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return dict(self.payload)


def test_terminal_coordinator_is_assembly_only(tmp_path) -> None:
    coordinator = GoalLoopTerminalCoordinator(
        repo_root=tmp_path,
        evidence_chain_summary=lambda goal_id: {"goal_id": goal_id},
    )
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
    marker = result["goal_loop_terminal_coordinator"]["execution_path"]
    assert result["goal_loop_terminal_coordinator"]["built_terminal_result"] is True
    assert marker["terminal_assembly_only"] is True
    assert marker["executes_tasks"] is False
    assert marker["persists_records"] is False
    assert marker["writes_evidence"] is False
    assert marker["mutates_runtime"] is False
    assert marker["mutates_memory"] is False
