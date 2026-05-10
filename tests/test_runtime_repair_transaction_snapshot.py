from __future__ import annotations

from core.tasks.runtime_repair_apply_executor_contract import (
    build_runtime_repair_apply_executor_contract,
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

from core.tasks.runtime_repair_transaction_snapshot import (
    build_runtime_repair_hydration_contract,
    build_runtime_repair_recovery_payload,
    build_runtime_repair_transaction_snapshot,
    summarize_runtime_repair_transaction_snapshot,
)


def _build_runtime_stack():
    tx = create_runtime_repair_transaction(
        task_id="task-snapshot",
        proposal_id="proposal-snapshot",
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

    controlled_apply = (
        build_runtime_repair_controlled_apply(
            tx,
            approved,
            target_paths=[
                "workspace/shared/demo.txt"
            ],
            requested_actions=[
                "prepare_code_repair"
            ],
        )
    )

    executor_contract = (
        build_runtime_repair_apply_executor_contract(
            controlled_apply
        )
    )

    return (
        tx,
        controlled_apply,
        executor_contract,
    )


def test_build_runtime_repair_transaction_snapshot() -> None:
    (
        tx,
        controlled_apply,
        executor_contract,
    ) = _build_runtime_stack()

    snapshot = (
        build_runtime_repair_transaction_snapshot(
            tx,
            controlled_apply=controlled_apply,
            executor_contract=executor_contract,
        )
    )

    assert (
        snapshot["snapshot_type"]
        == "runtime_repair_transaction_snapshot"
    )

    assert (
        snapshot["replay_safe"]
        is True
    )

    assert (
        snapshot["filesystem_persisted"]
        is False
    )

    assert (
        snapshot["transaction_id"]
        == tx["transaction_id"]
    )


def test_build_runtime_repair_recovery_payload() -> None:
    (
        tx,
        controlled_apply,
        executor_contract,
    ) = _build_runtime_stack()

    payload = (
        build_runtime_repair_recovery_payload(
            tx,
            controlled_apply=controlled_apply,
            executor_contract=executor_contract,
        )
    )

    assert (
        payload["payload_type"]
        == "runtime_repair_recovery_payload"
    )

    assert (
        payload["recovery_required"]
        is False
    )

    assert (
        payload["filesystem_recovery_required"]
        is False
    )


def test_build_runtime_repair_hydration_contract() -> None:
    (
        tx,
        controlled_apply,
        executor_contract,
    ) = _build_runtime_stack()

    contract = (
        build_runtime_repair_hydration_contract(
            tx,
            controlled_apply=controlled_apply,
            executor_contract=executor_contract,
        )
    )

    assert (
        contract["contract_type"]
        == "runtime_repair_hydration_contract"
    )

    assert (
        contract["replay_safe"]
        is True
    )

    assert (
        contract["hydration_allowed"]
        is True
    )

    assert (
        contract["filesystem_write_allowed"]
        is False
    )


def test_summarize_runtime_repair_transaction_snapshot() -> None:
    summary = (
        summarize_runtime_repair_transaction_snapshot(
            {
                "snapshot_id": "snapshot-1",
                "transaction_id": "tx-1",
                "task_id": "task-1",
                "proposal_id": "proposal-1",
                "transaction_state": "approved",
                "replay_safe": True,
                "filesystem_persisted": False,
            }
        )
    )

    assert (
        summary["snapshot_id"]
        == "snapshot-1"
    )

    assert (
        summary["transaction_state"]
        == "approved"
    )

    assert (
        summary["replay_safe"]
        is True
    )