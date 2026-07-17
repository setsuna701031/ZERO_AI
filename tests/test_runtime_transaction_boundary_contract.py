from __future__ import annotations

from core.runtime.governed_runtime_execution_session import (

    build_governed_runtime_execution_session_report,
)
from core.runtime.repair_transaction_execution_bridge import build_executable_repair_transaction
from core.runtime.runtime_transaction_context import (
    build_transaction_boundary_metadata,
    merge_current_transaction_metadata,
    transaction_context,
    RuntimeTransactionContext,
)
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



CANONICAL_TRANSACTION_FIELDS = {
    "transaction_id",
    "transaction_source",
    "transaction_status",
    "transaction_legality",
    "transaction_scope",
    "transaction_timestamp",
}


def test_legal_committed_transaction_boundary() -> None:
    boundary = build_transaction_boundary_metadata(
        {
            "transaction_id": "tx-1",
            "transaction_source": "runtime_execution_gateway",
            "transaction_status": "committed",
            "transaction_scope": "execution_gateway",
            "transaction_timestamp": "2026-05-24T00:00:00Z",
        }
    )

    assert CANONICAL_TRANSACTION_FIELDS <= set(boundary)
    assert boundary["transaction_status"] == "committed"
    assert boundary["transaction_legality"] == "legal"


def test_denied_transaction_cannot_commit() -> None:
    boundary = build_transaction_boundary_metadata(
        {
            "transaction_id": "tx-denied",
            "transaction_source": "runtime_execution_gateway",
            "transaction_status": "denied",
            "transaction_scope": "execution_gateway",
            "denial_reason": "policy_denied",
        }
    )

    assert boundary["transaction_status"] == "denied"
    assert boundary["transaction_legality"] == "denied"
    assert boundary["denial_reason"] == "policy_denied"


def test_failed_transaction_cannot_be_marked_committed() -> None:
    boundary = build_transaction_boundary_metadata(
        {
            "transaction_id": "tx-failed",
            "transaction_source": "governed_runtime_execution_session",
            "transaction_status": "failed",
            "transaction_scope": "governed_execution",
            "failure_reason": "execution_failed",
        }
    )

    assert boundary["transaction_status"] == "failed"
    assert boundary["transaction_legality"] == "failed"
    assert boundary["boundary_reason"] == "execution_failed"


def test_duplicate_transaction_propagation_preserves_evidence() -> None:
    boundary = build_transaction_boundary_metadata(
        {
            "transaction_id": "tx-outer",
            "transaction_source": "runtime_transaction_context",
            "transaction_status": "opened",
            "runtime_transaction": {
                "transaction_id": "tx-inner",
                "status": "committed",
                "provenance": {"source": "transaction_scope"},
            },
        }
    )

    assert boundary["transaction_legality"] == "duplicate"
    assert boundary["duplicate_transaction_propagation"] is True
    assert boundary["duplicate_transaction_evidence"]["transaction_id"] == "tx-inner"
    assert boundary["duplicate_transaction_evidence"]["transaction_status"] == "committed"


def test_incomplete_transaction_cannot_pretend_committed() -> None:
    boundary = build_transaction_boundary_metadata(
        {
            "transaction_status": "committed",
            "transaction_source": "runtime_execution_gateway",
            "transaction_scope": "execution_gateway",
        }
    )

    assert boundary["transaction_status"] == "committed"
    assert boundary["transaction_legality"] == "incomplete"
    assert boundary["boundary_reason"] == "incomplete_transaction_cannot_commit"


def test_current_transaction_metadata_propagates_boundary() -> None:
    context = RuntimeTransactionContext(
        transaction_id="tx-context",
        provenance={"source": "transaction_scope"},
        metadata={"transaction_scope": "unit_test"},
    )

    with transaction_context(context):
        metadata = merge_current_transaction_metadata({"operation": "test"})

    boundary = metadata["transaction_boundary"]
    assert boundary["transaction_id"] == "tx-context"
    assert boundary["transaction_source"] == "transaction_scope"
    assert boundary["transaction_status"] == "opened"
    assert boundary["transaction_scope"] == "unit_test"


def test_governed_execution_session_propagates_transaction_boundary() -> None:
    report = build_governed_runtime_execution_session_report(
        action_execution_report={
            "governed_action_execution_id": "exec-1",
            "transaction_id": "tx-governed",
            "execution_state": "blocked",
            "denial_reason": "review_required",
        }
    )

    boundary = report["transaction_boundary"]
    assert boundary["transaction_id"] == "tx-governed"
    assert boundary["transaction_source"] == "governed_runtime_execution_session"
    assert boundary["transaction_status"] == "denied"
    assert boundary["transaction_legality"] == "denied"


def test_repair_transaction_bridge_propagates_boundary_metadata_only() -> None:
    executable = build_executable_repair_transaction(
        {
            "transaction_type": "runtime_repair_transaction",
            "transaction_id": "repair-tx-1",
            "state": "committed",
            "created_at": "2026-05-24T00:00:00Z",
            "committed_mutations": [
                {
                    "raw_mutation": {
                        "op_type": "write_file",
                        "target_path": "project/example.py",
                        "content": "x",
                    }
                }
            ],
        }
    )

    boundary = executable["metadata"]["transaction_boundary"]
    assert boundary["transaction_id"] == "repair-tx-1"
    assert boundary["transaction_source"] == "repair_transaction_execution_bridge"
    assert boundary["transaction_scope"] == "repair_transaction_bridge"
