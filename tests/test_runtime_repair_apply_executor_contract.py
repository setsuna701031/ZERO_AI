from __future__ import annotations

from core.tasks.runtime_repair_apply_executor_contract import (
    build_runtime_repair_apply_executor_contract,
    build_runtime_repair_execution_audit_payload,
    build_runtime_repair_execution_receipt,
    build_runtime_repair_rollback_receipt,
)

from core.tasks.runtime_repair_controlled_apply import (
    build_runtime_repair_controlled_apply,
)

from core.tasks.runtime_repair_transaction import (
    create_runtime_repair_transaction,
    stage_runtime_repair_mutation,
)

from core.tasks.runtime_repair_transaction_review import (
    approve_runtime_repair_transaction_review,
    build_runtime_repair_transaction_review,
)


def _build_controlled_apply():
    tx = create_runtime_repair_transaction(
        task_id="task-executor",
        proposal_id="proposal-executor",
        scope_gate={
            "scope_allowed": True,
        },
    )

    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "prepare_code_repair",
            "target_path": "workspace/shared/demo.txt",
        },
    )

    tx["state"] = "approved"

    review = build_runtime_repair_transaction_review(
        tx
    )

    approved = approve_runtime_repair_transaction_review(
        review,
        operator="operator",
        reason="safe",
    )

    return build_runtime_repair_controlled_apply(
        tx,
        approved,
        target_paths=[
            "workspace/shared/demo.txt"
        ],
        requested_actions=[
            "prepare_code_repair"
        ],
    )


def test_build_runtime_repair_apply_executor_contract() -> None:
    controlled_apply = (
        _build_controlled_apply()
    )

    contract = (
        build_runtime_repair_apply_executor_contract(
            controlled_apply
        )
    )

    assert (
        contract["contract_type"]
        == "runtime_repair_apply_executor_contract"
    )

    assert (
        contract["dry_run_only"]
        is True
    )

    assert (
        contract["execution_allowed"]
        is False
    )

    assert (
        contract["real_mutation_allowed"]
        is False
    )

    assert (
        contract["filesystem_write_allowed"]
        is False
    )


def test_build_runtime_repair_execution_receipt() -> None:
    controlled_apply = (
        _build_controlled_apply()
    )

    receipt = (
        build_runtime_repair_execution_receipt(
            controlled_apply,
            contract_id="contract-1",
        )
    )

    assert (
        receipt["receipt_type"]
        == "runtime_repair_execution_receipt"
    )

    assert (
        receipt["execution_status"]
        == "dry_run_only"
    )

    assert (
        receipt["execution_performed"]
        is False
    )


def test_build_runtime_repair_rollback_receipt() -> None:
    controlled_apply = (
        _build_controlled_apply()
    )

    receipt = (
        build_runtime_repair_rollback_receipt(
            controlled_apply,
            contract_id="contract-1",
        )
    )

    assert (
        receipt["receipt_type"]
        == "runtime_repair_rollback_receipt"
    )

    assert (
        receipt["rollback_performed"]
        is False
    )


def test_build_runtime_repair_execution_audit_payload() -> None:
    controlled_apply = (
        _build_controlled_apply()
    )

    execution_receipt = {
        "receipt_type": (
            "runtime_repair_execution_receipt"
        )
    }

    rollback_receipt = {
        "receipt_type": (
            "runtime_repair_rollback_receipt"
        )
    }

    audit = (
        build_runtime_repair_execution_audit_payload(
            controlled_apply,
            execution_receipt=execution_receipt,
            rollback_receipt=rollback_receipt,
        )
    )

    assert (
        audit["audit_type"]
        == "runtime_repair_execution_audit"
    )

    assert (
        audit["dry_run_only"]
        is True
    )

    assert (
        audit["execution_allowed"]
        is False
    )