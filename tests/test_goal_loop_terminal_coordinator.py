from __future__ import annotations

from core.tasks.goal_loop_terminal_coordinator import GoalLoopTerminalCoordinator


class Runtime:
    def __init__(self, data):
        self.data = data

    def to_dict(self):
        return dict(self.data)


def test_terminal_coordinator_builds_result(tmp_path) -> None:
    coordinator = GoalLoopTerminalCoordinator(
        repo_root=tmp_path,
        evidence_chain_summary=lambda goal_id: {"goal_id": goal_id},
    )

    result = coordinator.build_result(
        target_goal_id="goal_a",
        current_goal_id="goal_a",
        terminal=True,
        stop_reason="complete",
        cycles=[
            {
                "adaptive_decision_record": {"decision": "complete"},
                "goal_completion_authority_result": {
                    "accepted": True,
                    "completed": True,
                    "from_state": "active",
                    "to_state": "completed",
                    "reason": "validated_evidence_and_subgoals_ready",
                    "evidence_refs": [{"evidence_id": "e1", "validation_state": "validated"}],
                },
            }
        ],
        max_cycles=1,
        max_replans=1,
        max_continuations=1,
        session_runtime=Runtime({"current_goal_id": "goal_a"}),
        continuation_runtime=Runtime({"continuation_count": 0}),
        replan_runtime=Runtime({"replan_count": 0}),
    )

    assert result["ok"] is True
    assert result["terminal"] is True
    assert result["stop_reason"] == "complete"
    assert result["goal_completion_authority_result"]["accepted"] is True
    assert result["goal_loop_terminal_coordinator"]["requires_goal_completion_authority"] is True
    assert result["goal_loop_terminal_coordinator"]["goal_completion_authority_accepted"] is True
    assert result["evidence_chain"]["goal_id"] == "goal_a"


def test_terminal_coordinator_rejects_complete_without_goal_completion_authority(tmp_path) -> None:
    coordinator = GoalLoopTerminalCoordinator(
        repo_root=tmp_path,
        evidence_chain_summary=lambda goal_id: {"goal_id": goal_id},
    )

    result = coordinator.build_result(
        target_goal_id="goal_a",
        current_goal_id="goal_a",
        terminal=True,
        stop_reason="complete",
        cycles=[
            {
                "adaptive_decision_record": {"decision": "complete"},
            }
        ],
        max_cycles=1,
        max_replans=1,
        max_continuations=1,
        session_runtime=Runtime({"current_goal_id": "goal_a"}),
        continuation_runtime=Runtime({"continuation_count": 0}),
        replan_runtime=Runtime({"replan_count": 0}),
    )

    assert result["ok"] is False
    assert result["terminal"] is True
    assert result["stop_reason"] == "goal_completion_authority_required"
    assert result["goal_completion_authority_result"] == {}
    assert result["goal_loop_terminal_coordinator"]["requires_goal_completion_authority"] is True
    assert result["goal_loop_terminal_coordinator"]["goal_completion_authority_accepted"] is False