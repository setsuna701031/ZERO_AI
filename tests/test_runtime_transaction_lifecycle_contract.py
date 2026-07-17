from __future__ import annotations

import pytest

from core.runtime.runtime_transaction_registry import (

    RuntimeTransactionState,
    assert_transaction_lifecycle_valid,
    create_transaction,
    list_transactions,
    record_apply,
    record_approval,
    record_audit,
    record_commit,
    record_failure,
    record_preflight,
    record_rollback,
    record_verification,
    transaction_to_dict,
)
pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



def test_transaction_state_order_cannot_skip() -> None:
    tx = _transaction("order")
    with pytest.raises(ValueError, match="invalid transaction transition"):
        record_apply(tx, {"ok": True})


def test_committed_requires_applied_and_verified_success() -> None:
    tx = record_preflight(_transaction("commit"), {"ok": True})
    tx = record_approval(tx, {"ok": True, "approved": True})
    tx = record_apply(tx, {"ok": True}, affected_files=["workspace/shared/commit.txt"])

    with pytest.raises(ValueError, match="verified success"):
        record_commit(tx, {"ok": True})

    tx = record_verification(tx, {"ok": True, "verification_ok": True})
    tx = record_commit(tx, {"ok": True, "committed": True})
    tx = record_audit(tx, ["audit:commit"])

    assert tx.state is RuntimeTransactionState.AUDITED
    assert assert_transaction_lifecycle_valid(tx) is True


def test_rolled_back_requires_applied_or_rollback_evidence() -> None:
    tx = _transaction("rollback")

    with pytest.raises(ValueError, match="rolled_back requires applied"):
        record_rollback(tx, {"ok": True, "rollback_applied": True})

    tx = record_preflight(tx, {"ok": True})
    tx = record_approval(tx, {"ok": True, "approved": True})
    tx = record_apply(tx, {"ok": True}, affected_files=["workspace/shared/rollback.txt"])
    tx = record_rollback(tx, {"ok": True, "rollback_applied": True, "evidence": "backup"})
    tx = record_audit(tx, ["audit:rollback"])

    assert assert_transaction_lifecycle_valid(tx) is True


def test_failed_state_records_reason() -> None:
    tx = record_preflight(_transaction("failed"), {"ok": True})
    tx = record_approval(tx, {"ok": True, "approved": True})
    tx = record_apply(tx, {"ok": True}, affected_files=["workspace/shared/failed.txt"])
    tx = record_failure(tx, "verification_failed")
    tx = record_audit(tx, ["audit:failed"])

    assert tx.failure_result["reason"] == "verification_failed"
    assert assert_transaction_lifecycle_valid(tx) is True


def test_transaction_queryable_by_task_step_trace() -> None:
    tx = _transaction("query")

    assert tx in list_transactions(task_id="task-query")
    assert tx in list_transactions(step_id="step-query")
    assert tx in list_transactions(trace_id="trace-query")


def test_transaction_serialization_is_stable() -> None:
    tx = _transaction("serialize")
    payload = transaction_to_dict(tx)

    assert list(payload) == [
        "transaction_id",
        "task_id",
        "step_id",
        "trace_id",
        "authority_source",
        "surface",
        "kind",
        "risk",
        "state",
        "affected_files",
        "preflight_result",
        "approval_result",
        "apply_result",
        "verification_result",
        "commit_result",
        "rollback_result",
        "failure_result",
        "audit_refs",
        "replay_refs",
        "parent_transaction_id",
        "replay_source",
        "original_transaction_id",
        "original_trace_id",
        "created_at",
        "updated_at",
        "state_history",
    ]
    assert payload["state"] == "proposed"


def test_anonymous_transaction_is_rejected() -> None:
    with pytest.raises(ValueError, match="anonymous transaction rejected"):
        create_transaction(
            task_id="",
            step_id="step-anon",
            trace_id="trace-anon",
            authority_source="execution_gateway",
            surface="write_file",
            affected_files=["workspace/shared/anon.txt"],
        )


def test_transaction_surface_must_exist_in_runtime_surface_registry() -> None:
    with pytest.raises(ValueError, match="registered mutation surface"):
        create_transaction(
            task_id="task-unknown",
            step_id="step-unknown",
            trace_id="trace-unknown",
            authority_source="execution_gateway",
            surface="anonymous_mutation_apply",
            affected_files=["workspace/shared/unknown.txt"],
        )


def test_mutation_transaction_has_affected_files_when_file_mutation() -> None:
    tx = _transaction("files")

    with pytest.raises(AssertionError, match="affected_files"):
        assert_transaction_lifecycle_valid(tx)

    tx = record_preflight(tx, {"ok": True})
    tx = record_approval(tx, {"ok": True, "approved": True})
    tx = record_apply(tx, {"ok": True}, affected_files=["workspace/shared/files.txt"])
    tx = record_verification(tx, {"ok": True, "verification_ok": True})
    tx = record_commit(tx, {"ok": True, "committed": True})
    tx = record_audit(tx, ["audit:files"])

    assert assert_transaction_lifecycle_valid(tx) is True


def _transaction(label: str):
    return create_transaction(
        task_id=f"task-{label}",
        step_id=f"step-{label}",
        trace_id=f"trace-{label}",
        authority_source="execution_gateway",
        surface="write_file",
    )
