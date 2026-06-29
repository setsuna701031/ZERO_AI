from __future__ import annotations

import pytest

from core.engineering.mutation_execution_readiness import (

    build_mutation_execution_readiness,
    validate_mutation_execution_readiness_contract,
)
pytestmark = [pytest.mark.contract]



def test_mutation_execution_readiness_allows_only_fully_gated_proposal() -> None:
    readiness = build_mutation_execution_readiness(
        _repair_proposal(),
        approval_complete=True,
        rollback_available=True,
        verification_profile_available=True,
    )
    payload = readiness.to_dict()

    assert payload["readiness_id"].startswith("mutation-readiness-")
    assert payload["ready_for_governed_mutation"] is True
    assert payload["blockers"] == []
    assert payload["approval_complete"] is True
    assert payload["rollback_available"] is True
    assert payload["verification_profile_available"] is True
    assert payload["mutation_scope_locked"] is True
    assert payload["metadata"]["control_plane_only"] is True
    assert payload["metadata"]["mutation_allowed"] is False
    assert payload["metadata"]["execution_allowed"] is False
    assert payload["metadata"]["governed_mutation_pipeline_required"] is True
    assert validate_mutation_execution_readiness_contract(payload) is True


def test_mutation_execution_readiness_blocks_missing_approval() -> None:
    payload = build_mutation_execution_readiness(
        _repair_proposal(),
        approval_complete=False,
        rollback_available=True,
        verification_profile_available=True,
    ).to_dict()

    assert payload["ready_for_governed_mutation"] is False
    assert "approval_incomplete" in payload["blockers"]
    assert validate_mutation_execution_readiness_contract(payload) is True


def test_mutation_execution_readiness_blocks_missing_rollback() -> None:
    payload = build_mutation_execution_readiness(
        _repair_proposal(),
        approval_complete=True,
        rollback_available=False,
        verification_profile_available=True,
    ).to_dict()

    assert payload["ready_for_governed_mutation"] is False
    assert "rollback_unavailable" in payload["blockers"]


def test_mutation_execution_readiness_blocks_missing_verification_profile() -> None:
    payload = build_mutation_execution_readiness(
        _repair_proposal(),
        approval_complete=True,
        rollback_available=True,
        verification_profile_available=False,
    ).to_dict()

    assert payload["ready_for_governed_mutation"] is False
    assert "verification_profile_unavailable" in payload["blockers"]


def test_mutation_execution_readiness_blocks_unlocked_scope() -> None:
    proposal = _repair_proposal()
    proposal["allowed_mutation_targets"] = []

    payload = build_mutation_execution_readiness(
        proposal,
        approval_complete=True,
        rollback_available=True,
        verification_profile_available=True,
    ).to_dict()

    assert payload["ready_for_governed_mutation"] is False
    assert "mutation_scope_unlocked" in payload["blockers"]


def test_mutation_execution_readiness_rejects_proposal_that_grants_authority() -> None:
    proposal = _repair_proposal()
    proposal["metadata"]["execution_allowed"] = True

    with pytest.raises(ValueError, match="repair_proposal_must_not_grant_execution_authority"):
        build_mutation_execution_readiness(
            proposal,
            approval_complete=True,
            rollback_available=True,
            verification_profile_available=True,
        )


def test_mutation_execution_readiness_contract_rejects_runtime_success_shape() -> None:
    payload = build_mutation_execution_readiness(
        _repair_proposal(),
        approval_complete=True,
        rollback_available=True,
        verification_profile_available=True,
    ).to_dict()

    assert validate_mutation_execution_readiness_contract(payload) is True

    payload["runtime_evidence_id"] = "runtime-evidence-123"

    assert validate_mutation_execution_readiness_contract(payload) is False


def _repair_proposal() -> dict[str, object]:
    return {
        "proposal_id": "governed-repair-proposal-123",
        "recommendation_id": "retry-repair-recommendation-123",
        "verification_route_id": "verification-route-123",
        "repair_scope": ["core/runtime/executor.py"],
        "allowed_mutation_targets": ["core/runtime/executor.py"],
        "approval_required": True,
        "rollback_required": True,
        "verification_required": True,
        "execution_allowed": False,
        "mutation_allowed": False,
        "metadata": {
            "control_plane_only": True,
            "read_only": True,
            "mutation_allowed": False,
            "execution_allowed": False,
            "patch_apply_allowed": False,
            "runtime_authority_granted": False,
            "canonical_runtime_success": False,
            "requires_governed_mutation_pipeline": True,
            "requires_rollback_eligibility": True,
            "requires_verification_before_success": True,
        },
    }
