from __future__ import annotations

import pytest

from core.runtime.runtime_authority import build_authority_metadata
from core.runtime.runtime_closure import CANONICAL_CLOSURE_FIELDS, build_runtime_closure_fields
from core.runtime.runtime_execution_result import build_runtime_execution_result
from core.runtime.runtime_lifecycle_context import propagate_lifecycle_status
from core.runtime.runtime_lifecycle_coordinator import RuntimeLifecycleCoordinator
from core.runtime.runtime_transaction_coordinator import RuntimeTransactionCoordinator
pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




def test_finalized_execution_rejects_overwrite_attempt() -> None:
    result = build_runtime_execution_result(
        {
            "ok": True,
            "status": "succeeded",
            "closure_status": "finalized",
            "overwrite_attempt": True,
            "execution_id": "exec-finalized",
            "authority_source": "runtime_execution_gateway",
            "authority_scope": "execution_gateway",
            "ownership_source": "core.runtime.executor",
        }
    )

    assert set(CANONICAL_CLOSURE_FIELDS) <= set(result)
    assert result["immutable_state"] is True
    assert result["ok"] is False
    assert result["executed"] is False
    assert result["closure_evidence"]["mismatch_evidence"][0]["kind"] == "overwrite_attempt"


def test_committed_transaction_reopen_rejected_with_evidence() -> None:
    coordinator = RuntimeTransactionCoordinator()
    coordinator.begin_transaction(transaction_id="tx-closure")
    coordinator.commit("tx-closure")

    with pytest.raises(RuntimeError):
        coordinator.bind_state("tx-closure", "state-late")

    scope = coordinator.get_scope("tx-closure")
    evidence = scope.metadata["closure_evidence"]["mismatch_evidence"]
    assert scope.to_metadata()["closure_status"] == "committed"
    assert any(item["kind"] == "reopen_attempt" for item in evidence)


def test_finalized_lifecycle_propagation_rejects_new_success_state() -> None:
    propagation = propagate_lifecycle_status("finalized", "executed")

    assert propagation["allowed"] is False
    assert propagation["status"] == "finalized"
    assert propagation["reason"] == "finalized_lifecycle_cannot_propagate_new_success_state"
    assert any(
        item["kind"] == "reopen_attempt"
        for item in propagation["closure_evidence"]["mismatch_evidence"]
    )


def test_lifecycle_coordinator_blocks_terminal_success_propagation_with_closure_evidence() -> None:
    coordinator = RuntimeLifecycleCoordinator()
    coordinator.create_record(
        lifecycle_id="life-closure",
        artifact_id="exec-closure",
        artifact_type="execution",
    )
    coordinator.mark_active("life-closure")
    coordinator.mark_verified("life-closure")
    coordinator.commit("life-closure")

    result = coordinator.transition("life-closure", "verified")

    assert result.status == "blocked"
    assert result.metadata["closure_status"] == "committed"
    assert any(
        item["kind"] == "reopen_attempt"
        for item in result.metadata["closure_evidence"]["mismatch_evidence"]
    )


def test_closed_authority_boundary_reacquire_rejected() -> None:
    authority = build_authority_metadata(
        {
            "authority_source": "unit",
            "authority_scope": "closed-scope",
            "authority_status": "allowed",
            "ownership_source": "core.runtime.executor",
            "closure_status": "closed",
        }
    )

    assert authority["authority_status"] == "closed_authority_boundary"
    assert authority["immutable_state"] is True
    assert any(
        item["kind"] == "authority_reacquire_attempt"
        for item in authority["closure_evidence"]["mismatch_evidence"]
    )


def test_duplicate_closure_propagation_preserves_evidence() -> None:
    closure = build_runtime_closure_fields(
        {
            "closure_status": "sealed",
            "runtime_closure": {
                "closure_status": "finalized",
                "closure_reason": "previous_finalization",
            },
        },
        artifact_type="execution",
        artifact_id="exec-duplicate",
    )

    assert closure["closure_status"] == "sealed"
    assert any(
        item["kind"] == "duplicate_closure_propagation"
        for item in closure["closure_evidence"]["mismatch_evidence"]
    )
