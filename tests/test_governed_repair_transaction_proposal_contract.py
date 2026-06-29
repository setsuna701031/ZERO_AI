from __future__ import annotations

import pytest

from core.engineering.governed_repair_transaction_proposal import (

    build_governed_repair_transaction_proposal,
    validate_governed_repair_transaction_proposal_contract,
)
pytestmark = [pytest.mark.contract]



def test_governed_repair_transaction_proposal_requires_repair_decision() -> None:
    proposal = build_governed_repair_transaction_proposal(
        _recommendation("recommend_repair"),
        repair_scope=["core/runtime/executor.py"],
        allowed_mutation_targets=["core/runtime/executor.py"],
    )
    payload = proposal.to_dict()

    assert payload["proposal_id"].startswith("governed-repair-proposal-")
    assert payload["approval_required"] is True
    assert payload["rollback_required"] is True
    assert payload["verification_required"] is True
    assert payload["execution_allowed"] is False
    assert payload["mutation_allowed"] is False
    assert payload["metadata"]["requires_governed_mutation_pipeline"] is True
    assert validate_governed_repair_transaction_proposal_contract(payload) is True


def test_governed_repair_transaction_proposal_rejects_non_repair_decision() -> None:
    with pytest.raises(ValueError, match="repair_proposal_requires_repair_recommendation"):
        build_governed_repair_transaction_proposal(
            _recommendation("retry_verification"),
            repair_scope=["core/runtime/executor.py"],
            allowed_mutation_targets=["core/runtime/executor.py"],
        )


def test_governed_repair_transaction_proposal_requires_scope() -> None:
    with pytest.raises(ValueError, match="repair_scope_required"):
        build_governed_repair_transaction_proposal(
            _recommendation("recommend_repair"),
            repair_scope=[],
            allowed_mutation_targets=["core/runtime/executor.py"],
        )


def test_governed_repair_transaction_contract_rejects_runtime_success_shape() -> None:
    payload = build_governed_repair_transaction_proposal(
        _recommendation("recommend_repair"),
        repair_scope=["core/runtime/executor.py"],
        allowed_mutation_targets=["core/runtime/executor.py"],
    ).to_dict()

    assert validate_governed_repair_transaction_proposal_contract(payload) is True

    payload["runtime_evidence_id"] = "runtime-evidence-123"

    assert validate_governed_repair_transaction_proposal_contract(payload) is False


def _recommendation(decision: str) -> dict[str, object]:
    return {
        "recommendation_id": "retry-repair-recommendation-123",
        "verification_route_id": "verification-route-123",
        "decision": decision,
        "metadata": {
            "control_plane_only": True,
            "mutation_allowed": False,
            "execution_allowed": False,
            "runtime_authority_granted": False,
            "canonical_runtime_success": False,
        },
    }
