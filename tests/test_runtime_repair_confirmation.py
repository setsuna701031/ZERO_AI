from __future__ import annotations

from core.tasks.runtime_repair_confirmation import (
    build_runtime_repair_confirmation_gate,
    build_runtime_repair_confirmation_gates,
)


def test_confirmation_gate_blocks_disallowed_proposal():
    proposal = {
        "task_id": "task_001",
        "proposal_allowed": False,
        "planner_allowed": False,
        "requires_confirmation": True,
        "reason": "scope requires confirmation before planner bridge",
    }

    gate = build_runtime_repair_confirmation_gate(proposal)

    assert gate["confirmation_status"] == "blocked"
    assert gate["planner_allowed_after_confirmation"] is False
    assert gate["mutation_allowed_after_confirmation"] is False
    assert gate["execution_allowed_after_confirmation"] is False
    assert gate["allowed_next_action"] == "inspect_bridge_reason"


def test_confirmation_gate_waits_for_required_confirmation():
    proposal = {
        "task_id": "task_002",
        "proposal_allowed": True,
        "planner_allowed": True,
        "requires_confirmation": True,
        "mutation_allowed": False,
        "execution_allowed": False,
    }

    gate = build_runtime_repair_confirmation_gate(proposal)

    assert gate["confirmation_status"] == "pending_confirmation"
    assert gate["planner_allowed_after_confirmation"] is False
    assert gate["confirmation_required_fields"] == ["approved", "operator", "reason"]
    assert gate["allowed_next_action"] == "request_operator_confirmation"


def test_confirmation_gate_approves_planner_proposal_after_confirmation():
    proposal = {
        "task_id": "task_003",
        "proposal_id": "proposal_003",
        "proposal_allowed": True,
        "planner_allowed": True,
        "requires_confirmation": True,
        "mutation_allowed": False,
        "execution_allowed": False,
    }
    confirmation = {
        "approved": True,
        "operator": "tester",
        "reason": "reviewed and approved for planner proposal only",
    }

    gate = build_runtime_repair_confirmation_gate(proposal, confirmation=confirmation)

    assert gate["proposal_id"] == "proposal_003"
    assert gate["confirmation_status"] == "approved"
    assert gate["operator"] == "tester"
    assert gate["planner_allowed_after_confirmation"] is True
    assert gate["mutation_allowed_after_confirmation"] is False
    assert gate["execution_allowed_after_confirmation"] is False
    assert gate["allowed_next_action"] == "planner_proposal_route_available"


def test_confirmation_gate_preserves_mutation_and_execution_limits():
    proposal = {
        "task_id": "task_004",
        "proposal_allowed": True,
        "planner_allowed": True,
        "requires_confirmation": True,
        "mutation_allowed": True,
        "execution_allowed": True,
    }
    confirmation = {"status": "approved"}

    gate = build_runtime_repair_confirmation_gate(proposal, confirmation=confirmation)

    assert gate["planner_allowed_after_confirmation"] is True
    assert gate["mutation_allowed_after_confirmation"] is True
    assert gate["execution_allowed_after_confirmation"] is True
    assert gate["allowed_next_action"] == "planner_execution_route_available"


def test_confirmation_gate_handles_rejection():
    proposal = {
        "task_id": "task_005",
        "proposal_allowed": True,
        "planner_allowed": True,
        "requires_confirmation": True,
    }
    confirmation = {"decision": "reject", "reason": "not safe enough"}

    gate = build_runtime_repair_confirmation_gate(proposal, confirmation=confirmation)

    assert gate["confirmation_status"] == "rejected"
    assert gate["planner_allowed_after_confirmation"] is False
    assert gate["reason"] == "not safe enough"
    assert gate["allowed_next_action"] == "archive_or_revise_proposal"


def test_confirmation_gate_accepts_single_or_list():
    gates = build_runtime_repair_confirmation_gates(
        [
            {"task_id": "task_a", "proposal_allowed": True, "planner_allowed": True, "requires_confirmation": False},
            {"task_id": "task_b", "proposal_allowed": False, "planner_allowed": False, "requires_confirmation": True},
        ]
    )

    assert len(gates) == 2
    assert gates[0]["confirmation_status"] == "not_required"
    assert gates[0]["planner_allowed_after_confirmation"] is True
    assert gates[1]["confirmation_status"] == "blocked"
