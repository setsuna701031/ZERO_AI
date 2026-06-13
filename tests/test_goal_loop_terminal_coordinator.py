from __future__ import annotations

from core.goals.goal_completion_authority import (
    GOAL_COMPLETION_AUTHORITY_OWNER,
    GOAL_COMPLETION_RESULT_SCHEMA,
)
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
                    "schema": GOAL_COMPLETION_RESULT_SCHEMA,
                    "authority_owner": GOAL_COMPLETION_AUTHORITY_OWNER,
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


def test_terminal_coordinator_preserves_rejected_authority_and_evidence(tmp_path) -> None:
    rejected = {
        "schema": GOAL_COMPLETION_RESULT_SCHEMA,
        "authority_owner": GOAL_COMPLETION_AUTHORITY_OWNER,
        "accepted": False,
        "completed": False,
        "from_state": "active",
        "to_state": "completed",
        "reason": "goal_lifecycle_contract_violation",
        "blocked_reason": "completed_goal_requires_validated_evidence",
        "evidence_refs": [{"evidence_id": "pending", "validation_state": "pending"}],
    }
    coordinator = GoalLoopTerminalCoordinator(repo_root=tmp_path)

    result = coordinator.build_result(
        target_goal_id="goal_a",
        current_goal_id="goal_a",
        terminal=True,
        stop_reason="complete",
        cycles=[
            {
                "adaptive_decision_record": {"decision": "complete"},
                "goal_completion_authority_result": rejected,
            }
        ],
    )

    assert result["ok"] is False
    assert result["stop_reason"] == "goal_completion_authority_required"
    assert result["goal_completion_authority_result"] == rejected


def test_terminal_coordinator_does_not_infer_authority_from_marker(tmp_path) -> None:
    coordinator = GoalLoopTerminalCoordinator(repo_root=tmp_path)

    result = coordinator.build_result(
        target_goal_id="goal_a",
        current_goal_id="goal_a",
        terminal=True,
        stop_reason="complete",
        cycles=[
            {
                "adaptive_decision_record": {
                    "decision": "complete",
                    "required_transition": {
                        "completion_authority": "GoalCompletionAuthority",
                        "to_state": "completed",
                        "evidence_refs": [{"evidence_id": "e1"}],
                    },
                },
            }
        ],
    )

    assert result["ok"] is False
    assert result["goal_completion_authority_result"] == {}
