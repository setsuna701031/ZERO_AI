from __future__ import annotations

from core.runtime.execution_gateway import build_runtime_execution_request
from core.runtime.governed_runtime_execution_session import (
    build_governed_runtime_execution_session_report,
)
from core.runtime.runtime_authority import build_authority_metadata
from core.runtime.runtime_execution_result import build_runtime_execution_result
from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
from core.runtime.runtime_transaction_context import (
    RuntimeTransactionContext,
    merge_current_transaction_metadata,
    transaction_context,
)


CANONICAL_AUTHORITY_FIELDS = {
    "authority_source",
    "authority_scope",
    "authority_status",
    "authority_reason",
    "ownership_source",
    "ownership_scope",
}


def test_legal_authority_execution_can_set_executed_true() -> None:
    result = build_runtime_execution_result(
        {
            "ok": True,
            "status": "succeeded",
            "authority_source": "runtime_execution_gateway",
            "authority_scope": "execution_gateway",
            "authority_status": "allowed",
            "authority_reason": "unit_authorized",
            "ownership_source": "core.runtime.executor",
            "ownership_scope": "execution_gateway",
        }
    )

    assert result["executed"] is True
    assert CANONICAL_AUTHORITY_FIELDS <= set(result)
    assert result["authority_status"] == "allowed"
    assert result["ownership_source"] == "core.runtime.executor"
    assert result["metadata"]["authority_seal"]["authority_status"] == "allowed"


def test_denied_authority_cannot_execution_commit() -> None:
    result = build_runtime_execution_result(
        {
            "ok": True,
            "executed": True,
            "authority_source": "runtime_execution_gateway",
            "authority_scope": "execution_gateway",
            "authority_status": "denied",
            "authority_reason": "policy_denied",
            "ownership_source": "core.runtime.executor",
            "ownership_scope": "execution_gateway",
        }
    )

    assert result["executed"] is False
    assert result["ok"] is False
    assert result["authority_status"] == "denied"
    assert result["authority_reason"] == "policy_denied"


def test_missing_ownership_rejects_executed_true_propagation() -> None:
    result = build_runtime_execution_result(
        {
            "ok": True,
            "executed": True,
            "authority_source": "runtime_execution_gateway",
            "authority_scope": "execution_gateway",
            "authority_status": "allowed",
        }
    )

    assert result["executed"] is False
    assert result["authority_status"] == "missing_ownership"
    assert result["authority_reason"] == "ownership_source_missing"


def test_authority_mismatch_preserves_evidence() -> None:
    authority = build_authority_metadata(
        {
            "authority_source": "runtime_execution_gateway",
            "authority_scope": "execution_gateway",
            "authority_status": "allowed",
            "ownership_source": "core.runtime.other_owner",
            "ownership_scope": "execution_gateway",
            "expected_ownership_source": "core.runtime.executor",
        }
    )

    assert authority["authority_status"] == "mismatch"
    assert authority["authority_mismatch_evidence"] == {
        "expected_ownership_source": "core.runtime.executor",
        "actual_ownership_source": "core.runtime.other_owner",
    }


def test_duplicate_authority_propagation_is_traceable() -> None:
    authority = build_authority_metadata(
        {
            "authority_source": "outer",
            "authority_scope": "outer_scope",
            "ownership_source": "outer_owner",
            "runtime_authority": {
                "authority_source": "inner",
                "authority_scope": "inner_scope",
                "authority_status": "allowed",
                "ownership_source": "inner_owner",
                "ownership_scope": "inner_scope",
            },
        }
    )

    assert authority["authority_status"] == "duplicate"
    assert authority["duplicate_authority_propagation"] is True
    assert authority["duplicate_authority_evidence"]["authority_source"] == "inner"


def test_closed_transaction_boundary_cannot_reacquire_authority() -> None:
    authority = build_authority_metadata(
        {
            "authority_source": "runtime_transaction_context",
            "authority_scope": "runtime_transaction",
            "authority_status": "allowed",
            "ownership_source": "core.runtime.runtime_transaction_context",
            "ownership_scope": "runtime_transaction",
            "transaction_boundary": {
                "transaction_id": "tx-closed",
                "transaction_status": "committed",
            },
        }
    )

    assert authority["authority_status"] == "closed_transaction_boundary"
    assert authority["closed_transaction_boundary"] is True


def test_execution_gateway_propagates_authority_metadata() -> None:
    request = build_runtime_execution_request(["echo", "ok"])

    assert request.metadata["authority_source"] == "core.runtime.execution_gateway"
    assert request.metadata["authority_status"] == "allowed"
    assert request.metadata["ownership_source"] == "core.runtime.executor"


def test_runtime_session_propagates_authority_metadata() -> None:
    session = RuntimeExecutionSessionManager().create_session("session-auth", "life-auth")

    assert session.authority_metadata["authority_source"] == "runtime"
    assert session.authority_metadata["authority_status"] == "allowed"
    assert session.authority_metadata["ownership_source"] == "core.runtime.runtime_execution_session"


def test_governed_execution_propagates_authority_metadata() -> None:
    report = build_governed_runtime_execution_session_report(
        action_execution_report={
            "governed_action_execution_id": "exec-auth",
            "execution_state": "blocked",
            "authority_reason": "review_required",
        }
    )

    assert report["authority_seal"]["authority_source"] == "governed_runtime_execution_session"
    assert report["authority_seal"]["authority_status"] == "denied"
    assert report["authority_seal"]["authority_reason"] == "review_required"


def test_transaction_metadata_flow_propagates_authority_seal() -> None:
    context = RuntimeTransactionContext(
        transaction_id="tx-auth",
        provenance={"source": "transaction_scope"},
    )

    with transaction_context(context):
        metadata = merge_current_transaction_metadata({})

    assert metadata["authority_seal"]["authority_source"] == "runtime_transaction_context"
    assert metadata["authority_seal"]["authority_status"] == "allowed"
    assert metadata["ownership_source"] == "core.runtime.runtime_transaction_context"
