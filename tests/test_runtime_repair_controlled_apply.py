from __future__ import annotations

from core.tasks.runtime_repair_controlled_apply import (
    build_runtime_repair_apply_plan,
    build_runtime_repair_controlled_apply,
    build_runtime_repair_rollback_plan,
)

from core.tasks.runtime_repair_transaction import (
    create_runtime_repair_transaction,
    stage_runtime_repair_mutation,
)

from core.tasks.runtime_repair_transaction_review import (
    approve_runtime_repair_transaction_review,
    build_runtime_repair_transaction_review,
)


def test_build_runtime_repair_controlled_apply_blocks_by_default() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-apply",
        proposal_id="proposal-apply",
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

    review = build_runtime_repair_transaction_review(tx)

    approved = approve_runtime_repair_transaction_review(
        review,
        operator="operator",
        reason="safe",
    )

    result = build_runtime_repair_controlled_apply(
        tx,
        approved,
        target_paths=[
            "workspace/shared/demo.txt",
        ],
        requested_actions=[
            "prepare_code_repair",
        ],
    )

    assert result["apply_type"] == "runtime_repair_controlled_apply"
    assert result["apply_allowed"] is False
    assert "mutation_authorization_blocked" in result["blocked_reasons"]
    assert result["execution_allowed"] is False
    assert result["mutation_execution_allowed"] is False
    assert result["apply_plan"]["dry_run_only"] is True
    assert result["apply_plan"]["apply_blocked_by_default"] is True


def test_build_runtime_repair_controlled_apply_blocks_unapproved_review() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-apply-blocked",
        proposal_id="proposal-apply-blocked",
        scope_gate={
            "scope_allowed": True,
        },
    )

    review = build_runtime_repair_transaction_review(tx)

    result = build_runtime_repair_controlled_apply(
        tx,
        review,
    )

    assert result["apply_allowed"] is False
    assert "review_not_approved" in result["blocked_reasons"]
    assert result["execution_allowed"] is False
    assert result["mutation_execution_allowed"] is False


def test_build_runtime_repair_apply_plan() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-plan",
        proposal_id="proposal-plan",
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

    plan = build_runtime_repair_apply_plan(
        tx,
        authorization={
            "authorization_status": "authorized",
        },
        scope_gate={
            "scope_status": "allowed",
        },
        target_paths=[
            "workspace/shared/demo.txt",
        ],
        requested_actions=[
            "prepare_code_repair",
        ],
    )

    assert plan["plan_type"] == "runtime_repair_apply_plan"
    assert plan["mutation_count"] == 1
    assert plan["dry_run_only"] is True
    assert plan["apply_blocked_by_default"] is True


def test_build_runtime_repair_rollback_plan() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-rollback",
        proposal_id="proposal-rollback",
        scope_gate={
            "scope_allowed": True,
        },
    )

    tx = stage_runtime_repair_mutation(
        tx,
        {
            "mutation_id": "mutation-1",
            "action": "prepare_code_repair",
            "target_path": "workspace/shared/demo.txt",
        },
    )

    rollback = build_runtime_repair_rollback_plan(
        tx,
        apply_plan={
            "plan_type": "runtime_repair_apply_plan",
        },
    )

    assert rollback["plan_type"] == "runtime_repair_rollback_plan"
    assert rollback["rollback_step_count"] == 1
    assert rollback["rollback_steps"][0]["target_path"] == "workspace/shared/demo.txt"