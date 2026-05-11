from __future__ import annotations

from core.tasks.runtime_repair_apply_executor_contract import (
    build_runtime_repair_apply_executor_contract,
)

from core.tasks.runtime_repair_controlled_apply import (
    build_runtime_repair_controlled_apply,
)

from core.tasks.runtime_repair_governance_boundary import (
    build_runtime_repair_governance_boundary,
)

from core.tasks.runtime_repair_persistence_contract import (
    build_runtime_repair_persistence_contract,
    build_runtime_repair_recovery_persistence_metadata,
    build_runtime_repair_replay_persistence_contract,
    build_runtime_repair_snapshot_persistence_contract,
    summarize_runtime_repair_persistence_contract,
)

from core.tasks.runtime_repair_replay_queue import (
    build_runtime_repair_replay_chain,
    build_runtime_repair_replay_queue_item,
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
    build_runtime_repair_transaction_snapshot,
)


def _build_runtime_stack():
    tx = create_runtime_repair_transaction(
        task_id="task-persistence",
        proposal_id="proposal-persistence",
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

    snapshot = (
        build_runtime_repair_transaction_snapshot(
            tx,
            controlled_apply=controlled_apply,
            executor_contract=executor_contract,
        )
    )

    queue_item = (
        build_runtime_repair_replay_queue_item(
            snapshot
        )
    )

    replay_chain = (
        build_runtime_repair_replay_chain(
            [queue_item]
        )
    )

    governance_boundary = (
        build_runtime_repair_governance_boundary(
            replay_chain=replay_chain,
            snapshot=snapshot,
            executor_contract=executor_contract,
        )
    )

    return (
        snapshot,
        replay_chain,
        governance_boundary,
    )


def test_build_runtime_repair_persistence_contract() -> None:
    (
        snapshot,
        replay_chain,
        governance_boundary,
    ) = _build_runtime_stack()

    contract = (
        build_runtime_repair_persistence_contract(
            snapshot=snapshot,
            replay_chain=replay_chain,
            governance_boundary=governance_boundary,
        )
    )

    assert (
        contract["contract_type"]
        == "runtime_repair_persistence_contract"
    )

    assert (
        contract["journal_safe"]
        is True
    )

    assert (
        contract["restoration_safe"]
        is True
    )

    assert (
        contract["filesystem_write_allowed"]
        is False
    )

    assert (
        contract["sqlite_allowed"]
        is False
    )


def test_build_runtime_repair_snapshot_persistence_contract() -> None:
    (
        snapshot,
        _,
        _,
    ) = _build_runtime_stack()

    contract = (
        build_runtime_repair_snapshot_persistence_contract(
            snapshot
        )
    )

    assert (
        contract["contract_type"]
        == "runtime_repair_snapshot_persistence_contract"
    )

    assert (
        contract["journal_safe"]
        is True
    )

    assert (
        contract["filesystem_persisted"]
        is False
    )


def test_build_runtime_repair_replay_persistence_contract() -> None:
    (
        _,
        replay_chain,
        _,
    ) = _build_runtime_stack()

    contract = (
        build_runtime_repair_replay_persistence_contract(
            replay_chain
        )
    )

    assert (
        contract["contract_type"]
        == "runtime_repair_replay_persistence_contract"
    )

    assert (
        contract["replay_safe"]
        is True
    )

    assert (
        contract["scheduler_resume_allowed"]
        is False
    )


def test_build_runtime_repair_recovery_persistence_metadata() -> None:
    (
        snapshot,
        replay_chain,
        governance_boundary,
    ) = _build_runtime_stack()

    metadata = (
        build_runtime_repair_recovery_persistence_metadata(
            snapshot,
            replay_chain,
            governance_boundary,
        )
    )

    assert (
        metadata["metadata_type"]
        == "runtime_repair_recovery_persistence_metadata"
    )

    assert (
        metadata["restoration_safe"]
        is True
    )

    assert (
        metadata["filesystem_resume_allowed"]
        is False
    )


def test_summarize_runtime_repair_persistence_contract() -> None:
    summary = (
        summarize_runtime_repair_persistence_contract(
            {
                "contract_id": "contract-1",
                "transaction_id": "tx-1",
                "journal_safe": True,
                "restoration_safe": True,
                "filesystem_write_allowed": False,
            }
        )
    )

    assert (
        summary["contract_id"]
        == "contract-1"
    )

    assert (
        summary["journal_safe"]
        is True
    )

    assert (
        summary["filesystem_write_allowed"]
        is False
    )