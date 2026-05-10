from __future__ import annotations

from core.tasks.runtime_repair_apply_executor_contract import (
    build_runtime_repair_apply_executor_contract,
)

from core.tasks.runtime_repair_controlled_apply import (
    build_runtime_repair_controlled_apply,
)

from core.tasks.runtime_repair_replay_queue import (
    build_runtime_repair_recovery_continuation_metadata,
    build_runtime_repair_replay_chain,
    build_runtime_repair_replay_queue_item,
    summarize_runtime_repair_replay_queue,
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


def _build_snapshot():
    tx = create_runtime_repair_transaction(
        task_id="task-replay",
        proposal_id="proposal-replay",
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

    return build_runtime_repair_transaction_snapshot(
        tx,
        controlled_apply=controlled_apply,
        executor_contract=executor_contract,
    )


def test_build_runtime_repair_replay_queue_item() -> None:
    snapshot = _build_snapshot()

    item = (
        build_runtime_repair_replay_queue_item(
            snapshot
        )
    )

    assert (
        item["queue_item_type"]
        == "runtime_repair_replay_queue_item"
    )

    assert (
        item["queue_status"]
        == "queued"
    )

    assert (
        item["replay_safe"]
        is True
    )

    assert (
        item["continuation_allowed"]
        is True
    )


def test_build_runtime_repair_replay_chain() -> None:
    snapshot = _build_snapshot()

    item = (
        build_runtime_repair_replay_queue_item(
            snapshot
        )
    )

    chain = (
        build_runtime_repair_replay_chain(
            [item]
        )
    )

    assert (
        chain["chain_type"]
        == "runtime_repair_replay_chain"
    )

    assert (
        chain["queue_item_count"]
        == 1
    )

    assert (
        chain["replay_safe"]
        is True
    )


def test_build_runtime_repair_recovery_continuation_metadata() -> None:
    snapshot = _build_snapshot()

    item = (
        build_runtime_repair_replay_queue_item(
            snapshot
        )
    )

    chain = (
        build_runtime_repair_replay_chain(
            [item]
        )
    )

    metadata = (
        build_runtime_repair_recovery_continuation_metadata(
            chain
        )
    )

    assert (
        metadata["metadata_type"]
        == "runtime_repair_recovery_continuation_metadata"
    )

    assert (
        metadata["continuation_allowed"]
        is True
    )

    assert (
        metadata["scheduler_resume_allowed"]
        is False
    )

    assert (
        metadata["filesystem_resume_allowed"]
        is False
    )


def test_summarize_runtime_repair_replay_queue() -> None:
    summary = (
        summarize_runtime_repair_replay_queue(
            {
                "chain_id": "chain-1",
                "queue_item_count": 2,
                "replay_safe": True,
                "continuation_allowed": True,
            }
        )
    )

    assert (
        summary["chain_id"]
        == "chain-1"
    )

    assert (
        summary["queue_item_count"]
        == 2
    )

    assert (
        summary["replay_safe"]
        is True
    )