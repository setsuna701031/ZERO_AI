from __future__ import annotations

from core.tasks.runtime_repair_apply_executor_contract import (
    build_runtime_repair_apply_executor_contract,
)

from core.tasks.runtime_repair_controlled_apply import (
    build_runtime_repair_controlled_apply,
)

from core.tasks.runtime_repair_governance_boundary import (
    build_runtime_repair_agent_loop_boundary_summary,
    build_runtime_repair_governance_boundary,
    build_runtime_repair_recovery_boundary_summary,
    build_runtime_repair_scheduler_boundary_summary,
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
        task_id="task-boundary",
        proposal_id="proposal-boundary",
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

    return (
        replay_chain,
        snapshot,
        executor_contract,
    )


def test_build_runtime_repair_governance_boundary() -> None:
    (
        replay_chain,
        snapshot,
        executor_contract,
    ) = _build_runtime_stack()

    boundary = (
        build_runtime_repair_governance_boundary(
            replay_chain=replay_chain,
            snapshot=snapshot,
            executor_contract=executor_contract,
        )
    )

    assert (
        boundary["boundary_type"]
        == "runtime_repair_governance_boundary"
    )

    assert (
        boundary["execution_allowed"]
        is False
    )

    assert (
        boundary["scheduler_resume_allowed"]
        is False
    )

    assert (
        boundary["filesystem_resume_allowed"]
        is False
    )


def test_build_runtime_repair_scheduler_boundary_summary() -> None:
    (
        replay_chain,
        snapshot,
        executor_contract,
    ) = _build_runtime_stack()

    summary = (
        build_runtime_repair_scheduler_boundary_summary(
            replay_chain,
            snapshot,
            executor_contract,
        )
    )

    assert (
        summary["summary_type"]
        == "runtime_repair_scheduler_boundary_summary"
    )

    assert (
        summary["replay_safe"]
        is True
    )

    assert (
        summary["scheduler_resume_allowed"]
        is False
    )


def test_build_runtime_repair_agent_loop_boundary_summary() -> None:
    (
        replay_chain,
        snapshot,
        executor_contract,
    ) = _build_runtime_stack()

    summary = (
        build_runtime_repair_agent_loop_boundary_summary(
            replay_chain,
            snapshot,
            executor_contract,
        )
    )

    assert (
        summary["summary_type"]
        == "runtime_repair_agent_loop_boundary_summary"
    )

    assert (
        summary["continuation_allowed"]
        is True
    )

    assert (
        summary["filesystem_write_allowed"]
        is False
    )


def test_build_runtime_repair_recovery_boundary_summary() -> None:
    (
        replay_chain,
        snapshot,
        executor_contract,
    ) = _build_runtime_stack()

    summary = (
        build_runtime_repair_recovery_boundary_summary(
            replay_chain,
            snapshot,
            executor_contract,
        )
    )

    assert (
        summary["summary_type"]
        == "runtime_repair_recovery_boundary_summary"
    )

    assert (
        summary["replay_safe"]
        is True
    )

    assert (
        summary["filesystem_resume_allowed"]
        is False
    )