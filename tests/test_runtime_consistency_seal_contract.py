from __future__ import annotations

from core.runtime.execution_gateway import build_runtime_execution_request
from core.runtime.governed_runtime_execution_session import (
    build_governed_runtime_execution_session_report,
)
from core.runtime.runtime_consistency import build_runtime_state_consistency
from core.runtime.runtime_execution_result import build_runtime_execution_result
from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
from core.runtime.runtime_transaction_coordinator import RuntimeTransactionCoordinator


CANONICAL_CONSISTENCY_FIELDS = {
    "consistency_status",
    "consistency_reason",
    "mismatch_evidence",
    "runtime_state_snapshot",
}


def _authority(status: str = "allowed", ownership_source: str = "core.runtime.executor") -> dict[str, str]:
    return {
        "authority_source": "runtime_execution_gateway",
        "authority_scope": "execution_gateway",
        "authority_status": status,
        "authority_reason": "unit_authority",
        "ownership_source": ownership_source,
        "ownership_scope": "execution_gateway",
    }


def _transaction(status: str = "opened", legality: str = "legal") -> dict[str, str]:
    return {
        "transaction_id": "tx-consistency",
        "transaction_source": "unit",
        "transaction_status": status,
        "transaction_legality": legality,
        "transaction_scope": "execution_gateway",
        "transaction_timestamp": "",
    }


def test_legal_consistent_runtime_state() -> None:
    seal = build_runtime_state_consistency(
        {
            **_authority(),
            "transaction_boundary": _transaction("opened"),
            "lifecycle_status": "running",
            "execution_status": "executed",
            "executed": True,
            "ok": True,
        }
    )

    assert CANONICAL_CONSISTENCY_FIELDS <= set(seal)
    assert seal["consistency_status"] == "consistent"
    assert seal["mismatch_evidence"] == []
    assert seal["runtime_state_snapshot"]["authority_status"] == "allowed"


def test_authority_transaction_mismatch_preserves_evidence() -> None:
    seal = build_runtime_state_consistency(
        {
            **_authority("denied"),
            "transaction_boundary": _transaction("committed"),
            "execution_status": "executed",
            "executed": True,
        }
    )

    assert seal["consistency_status"] == "mismatch"
    assert seal["consistency_reason"] == "runtime_state_mismatch"
    assert seal["mismatch_evidence"][0]["kind"] == "authority_transaction_mismatch"
    assert seal["runtime_state_snapshot"]["transaction_status"] == "committed"


def test_lifecycle_execution_mismatch_preserves_evidence() -> None:
    result = build_runtime_execution_result(
        {
            **_authority(),
            "status": "failed",
            "failed": True,
            "lifecycle_status": "finished",
        }
    )

    assert result["consistency_status"] == "mismatch"
    assert result["executed"] is False
    assert any(
        item["kind"] == "lifecycle_execution_mismatch"
        for item in result["mismatch_evidence"]
    )
    assert result["metadata"]["consistency_seal"]["consistency_status"] == "mismatch"


def test_blocked_lifecycle_rejects_success_execution_propagation() -> None:
    result = build_runtime_execution_result(
        {
            **_authority(),
            "ok": True,
            "executed": True,
            "status": "succeeded",
            "lifecycle_status": "blocked",
        }
    )

    assert result["executed"] is False
    assert result["ok"] is False
    assert result["consistency_status"] == "mismatch"
    assert any(
        item["kind"] == "blocked_lifecycle_execution_mismatch"
        for item in result["mismatch_evidence"]
    )


def test_rejected_transaction_rejects_executed_true_propagation() -> None:
    result = build_runtime_execution_result(
        {
            **_authority(),
            "ok": True,
            "executed": True,
            "transaction_boundary": _transaction("denied", "denied"),
        }
    )

    assert result["executed"] is False
    assert result["consistency_status"] == "mismatch"
    assert any(
        item["kind"] == "transaction_execution_mismatch"
        for item in result["mismatch_evidence"]
    )


def test_missing_ownership_cannot_propagate_committed_state() -> None:
    seal = build_runtime_state_consistency(
        {
            "authority_status": "missing_ownership",
            "transaction_boundary": _transaction("committed"),
        }
    )

    assert seal["consistency_status"] == "mismatch"
    assert any(
        item["kind"] == "ownership_transaction_mismatch"
        for item in seal["mismatch_evidence"]
    )


def test_duplicate_mismatch_evidence_is_traceable() -> None:
    seal = build_runtime_state_consistency(
        {
            **_authority(),
            "runtime_consistency": {
                "consistency_status": "mismatch",
                "consistency_reason": "previous_mismatch",
            },
        }
    )

    assert seal["consistency_status"] == "mismatch"
    assert seal["duplicate_consistency_mismatch"] is True
    assert seal["duplicate_consistency_evidence"]["consistency_reason"] == "previous_mismatch"


def test_execution_gateway_propagates_consistency_seal() -> None:
    request = build_runtime_execution_request(["echo", "ok"])

    assert request.metadata["consistency_seal"]["consistency_status"] == "consistent"
    assert "runtime_state_snapshot" in request.metadata["consistency_seal"]


def test_runtime_execution_session_propagates_consistency_metadata() -> None:
    manager = RuntimeExecutionSessionManager()
    session = manager.create_session("session-consistency", "life-consistency")

    assert session.consistency_metadata["consistency_status"] == "consistent"
    assert session.consistency_metadata["runtime_state_snapshot"]["lifecycle_status"] == "queued"


def test_transaction_coordinator_propagates_consistency_seal() -> None:
    coordinator = RuntimeTransactionCoordinator()
    coordinator.begin_transaction(transaction_id="tx-consistency-flow")
    result = coordinator.bind_execution(
        "tx-consistency-flow",
        "exec-consistency-flow",
        metadata={
            **_authority(),
            "transaction_boundary": _transaction("opened"),
            "execution_status": "executed",
        },
    ).to_metadata()

    assert result["metadata"]["consistency_seal"]["consistency_status"] == "consistent"
    assert result["metadata"]["consistency_seal"]["runtime_state_snapshot"]["execution_status"] == "executed"


def test_governed_execution_session_propagates_consistency_seal() -> None:
    report = build_governed_runtime_execution_session_report(
        action_execution_report={
            "governed_action_execution_id": "exec-consistency",
            "execution_state": "blocked",
            "denial_reason": "blocked_by_policy",
        }
    )

    assert report["consistency_seal"]["consistency_status"] == "consistent"
    assert report["consistency_seal"]["runtime_state_snapshot"]["lifecycle_status"] == "blocked"
