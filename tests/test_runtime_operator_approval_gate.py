from __future__ import annotations

import copy

import pytest

from core.runtime.runtime_operator_approval_gate import (
    RuntimeOperatorApprovalGate,
    evaluate_expiration,
)


NOW = "2026-07-10T12:00:00+00:00"


def _proposal(**updates: object) -> dict:
    proposal = {
        "schema": "zero.runtime.change_proposal_engine.v1",
        "ok": True,
        "proposal_status": "proposal_created",
        "proposal_id": "change-proposal-one",
        "requires_operator_approval": True,
        "mutation_allowed": False,
        "autonomous_apply_allowed": False,
        "patch_generation_allowed": False,
        "proposal": {
            "target_files": ["workspace/a.txt", "workspace/b.txt"],
            "recommended_actions": ["review_target_file"],
            "validation_requirements": ["run_focused_validation"],
            "rollback_requirements": [{"rollback_plan_required": True}],
        },
    }
    proposal.update(updates)
    return proposal


def _gate() -> RuntimeOperatorApprovalGate:
    return RuntimeOperatorApprovalGate(clock=lambda: NOW)


def test_valid_approve_is_deterministic_audited_and_non_executable() -> None:
    proposal = _proposal()
    before = copy.deepcopy(proposal)
    first = _gate().review(
        proposal=proposal, decision="approve", operator_id="operator", reason="reviewed"
    )
    second = _gate().review(
        proposal=proposal, decision="approve", operator_id="operator", reason="reviewed"
    )

    assert proposal == before
    assert first["approval_status"] == "approved"
    assert first["approval_id"] == second["approval_id"]
    assert first["proposal_fingerprint"] == second["proposal_fingerprint"]
    assert first["scope_fingerprint"] == second["scope_fingerprint"]
    assert first["execution_authority_granted"] is False
    assert first["mutation_allowed"] is False
    assert first["patch_application_allowed"] is False
    assert first["repair_execution_allowed"] is False
    assert first["autonomous_apply_allowed"] is False
    assert first["decision_authority"] is False
    assert first["requested_changes_modified"] is False
    assert first["requires_controlled_apply"] is True
    audit = first["audit_record"]
    assert audit["event_type"] == "operator_approval_reviewed"
    assert audit["security_invariants"]["execution_authority_granted"] is False


def test_valid_subset_scope_can_be_approved() -> None:
    result = _gate().review(
        proposal=_proposal(), decision="approve", operator_id="operator",
        approved_scope={
            "target_files": ["workspace/a.txt"],
            "recommended_actions": [],
            "validation_requirements": ["run_focused_validation"],
            "rollback_requirements": [],
        },
    )
    assert result["approval_status"] == "approved"
    assert result["approved_scope"]["target_files"] == ["workspace/a.txt"]


@pytest.mark.parametrize("scope", [
    {"target_files": ["workspace/new.txt"]},
    {"target_files": ["C:\\absolute.txt"]},
    {"target_files": ["../escape.txt"]},
])
def test_expanded_or_unsafe_scope_is_rejected(scope: dict) -> None:
    result = _gate().review(
        proposal=_proposal(), decision="approve", operator_id="operator",
        approved_scope=scope,
    )
    assert result["approval_status"] == "invalid_scope"
    assert result["ok"] is False


def test_reject_requires_reason_and_has_empty_scope() -> None:
    missing = _gate().review(
        proposal=_proposal(), decision="reject", operator_id="operator"
    )
    rejected = _gate().review(
        proposal=_proposal(), decision="reject", operator_id="operator",
        reason="unsafe scope",
    )
    assert missing["approval_status"] == "invalid_decision"
    assert rejected["approval_status"] == "rejected"
    assert all(not values for values in rejected["approved_scope"].values())


@pytest.mark.parametrize(("updates", "reason"), [
    ({"schema": "wrong"}, "invalid_proposal_schema"),
    ({"proposal_id": ""}, "proposal_id_required"),
    ({"mutation_allowed": True}, "proposal_mutation_boundary_invalid"),
    ({"autonomous_apply_allowed": True}, "proposal_autonomous_apply_boundary_invalid"),
])
def test_invalid_proposals_are_rejected(updates: dict, reason: str) -> None:
    result = _gate().review(
        proposal=_proposal(**updates), decision="approve", operator_id="operator"
    )
    assert result["approval_status"] == "invalid_proposal"
    assert result["reason"] == reason


def test_empty_operator_and_invalid_decision_are_rejected() -> None:
    operator = _gate().review(
        proposal=_proposal(), decision="approve", operator_id=""
    )
    decision = _gate().review(
        proposal=_proposal(), decision="maybe", operator_id="operator"
    )
    assert operator["approval_status"] == "invalid_operator"
    assert decision["approval_status"] == "invalid_decision"


def test_expiration_is_deterministic_and_pure() -> None:
    expired = _gate().review(
        proposal=_proposal(), decision="approve", operator_id="operator",
        expires_at="2026-07-10T11:59:00+00:00",
    )
    active = _gate().review(
        proposal=_proposal(), decision="approve", operator_id="operator",
        expires_at="2026-07-10T13:00:00+00:00",
    )
    before = copy.deepcopy(active)
    evaluated = evaluate_expiration(active, "2026-07-10T14:00:00+00:00")

    assert expired["approval_status"] == "expired"
    assert expired["expired"] is True
    assert evaluated["approval_status"] == "expired"
    assert active == before


def test_revoke_only_active_approved_record() -> None:
    approved = _gate().review(
        proposal=_proposal(), decision="approve", operator_id="operator"
    )
    before = copy.deepcopy(approved)
    revoked = _gate().revoke(approved, "reviewer", "withdraw approval")
    rejected = _gate().review(
        proposal=_proposal(), decision="reject", operator_id="operator", reason="no"
    )
    invalid = _gate().revoke(rejected, "reviewer", "withdraw")

    assert approved == before
    assert revoked["approval_status"] == "revoked"
    assert revoked["revoked"] is True
    assert revoked["execution_authority_granted"] is False
    assert revoked["audit_record"]["event_type"] == "operator_approval_revoked"
    assert invalid["approval_status"] == "invalid_decision"
