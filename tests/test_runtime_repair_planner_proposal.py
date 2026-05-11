from __future__ import annotations

from core.tasks.runtime_repair_planner_proposal import (
    build_runtime_repair_planner_proposal,
    build_runtime_repair_planner_proposals,
)


def test_planner_proposal_blocks_when_bridge_disallows_planner():
    proposal = build_runtime_repair_planner_proposal(
        {
            "task_id": "task_001",
            "status": "failed",
            "planner_allowed": False,
            "requires_confirmation": True,
            "repair_scope": "code_execution_review",
            "repair_risk": "high",
            "reason": "confirmation required",
            "allowed_actions": ["inspect_trace", "propose_repair_plan"],
            "blocked_actions": ["apply_patch", "write_file"],
            "repair_intent": {
                "intent_type": "inspect_code_execution_failure",
                "scope": "code_execution_review",
                "risk": "high",
                "mode": "manual_review",
            },
        }
    )

    assert proposal["ok"] is True
    assert proposal["proposal_allowed"] is False
    assert proposal["proposal_mode"] == "blocked"
    assert proposal["planner_allowed"] is False
    assert proposal["requires_confirmation"] is True
    assert proposal["repair_intent"]["intent_type"] == "inspect_code_execution_failure"
    assert "apply_patch" in proposal["blocked_actions"]
    assert "Planner proposal is blocked" in proposal["human_summary"]


def test_planner_proposal_review_only_when_confirmation_required():
    proposal = build_runtime_repair_planner_proposal(
        {
            "task_id": "task_002",
            "status": "failed",
            "planner_allowed": True,
            "requires_confirmation": True,
            "bridge_mode": "read_only_planner_gate",
            "repair_scope": "verification",
            "repair_risk": "medium",
            "allowed_actions": ["inspect_result", "propose_repair_plan"],
            "blocked_actions": ["apply_patch"],
            "inspection_targets": ["result.json", "trace.json"],
            "repair_intent": {
                "intent_type": "inspect_verification_failure",
                "scope": "verification",
                "risk": "medium",
                "mode": "guided_repair_plan",
            },
        }
    )

    assert proposal["proposal_allowed"] is True
    assert proposal["proposal_mode"] == "review_only"
    assert proposal["proposed_actions"] == ["inspect_result", "propose_repair_plan"]
    assert proposal["inspection_targets"] == ["result.json", "trace.json"]
    assert proposal["repair_intent"]["mutation_allowed"] is False
    assert proposal["repair_intent"]["execution_allowed"] is False


def test_planner_proposal_proposal_only_when_safe_and_no_confirmation():
    proposal = build_runtime_repair_planner_proposal(
        {
            "task_id": "task_003",
            "planner_allowed": True,
            "requires_confirmation": False,
            "bridge_mode": "read_only_planner_gate",
            "repair_scope": "read_only",
            "repair_risk": "low",
            "allowed_actions": ["inspect_runtime_state", "propose_repair_plan"],
            "repair_intent": {
                "intent_type": "observe_running_task",
                "mode": "guided_repair_plan",
            },
        }
    )

    assert proposal["proposal_allowed"] is True
    assert proposal["proposal_mode"] == "proposal_only"
    assert "inspect_runtime_state" in proposal["proposed_actions"]
    assert "apply_patch" in proposal["blocked_actions"]


def test_planner_proposal_strips_mutating_actions_even_if_allowed_by_input():
    proposal = build_runtime_repair_planner_proposal(
        {
            "planner_allowed": True,
            "requires_confirmation": False,
            "bridge_mode": "read_only_planner_gate",
            "allowed_actions": ["inspect_trace", "apply_patch", "write_file", "propose_repair_plan"],
            "blocked_actions": ["delete_file"],
        }
    )

    assert "inspect_trace" in proposal["proposed_actions"]
    assert "propose_repair_plan" in proposal["proposed_actions"]
    assert "apply_patch" not in proposal["proposed_actions"]
    assert "write_file" not in proposal["proposed_actions"]
    assert "delete_file" in proposal["blocked_actions"]


def test_planner_proposal_hard_blocks_mutation_or_execution_gate():
    mutation_proposal = build_runtime_repair_planner_proposal(
        {
            "planner_allowed": True,
            "requires_confirmation": False,
            "mutation_allowed": True,
            "allowed_actions": ["propose_repair_plan"],
        }
    )
    execution_proposal = build_runtime_repair_planner_proposal(
        {
            "planner_allowed": True,
            "requires_confirmation": False,
            "execution_allowed": True,
            "allowed_actions": ["propose_repair_plan"],
        }
    )

    assert mutation_proposal["proposal_allowed"] is False
    assert mutation_proposal["proposal_mode"] == "blocked"
    assert execution_proposal["proposal_allowed"] is False
    assert execution_proposal["proposal_mode"] == "blocked"


def test_planner_proposals_accepts_single_or_list():
    one = build_runtime_repair_planner_proposals({"planner_allowed": False})
    many = build_runtime_repair_planner_proposals(
        [
            {"planner_allowed": False},
            {"planner_allowed": True, "allowed_actions": ["inspect_trace"]},
        ]
    )

    assert len(one) == 1
    assert len(many) == 2
    assert one[0]["proposal_type"] == "runtime_repair_planner_proposal"
