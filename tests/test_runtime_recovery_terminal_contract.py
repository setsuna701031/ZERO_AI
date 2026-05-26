from __future__ import annotations

from core.runtime.runtime_recovery_freeze import (
    assert_recovery_does_not_overwrite_source_transaction,
    assert_recovery_terminal_state,
    build_recovery_decision,
    create_recovery_attempt,
    create_recovery_transaction,
    list_recovery_attempts,
    record_recovery_apply,
    record_recovery_commit,
    record_recovery_preflight,
    record_recovery_requires_human_review,
    record_recovery_rollback,
    record_recovery_terminal_failure,
    record_recovery_verify,
    transaction_recovery_lineage,
)
from core.runtime.runtime_transaction_registry import create_transaction, get_transaction, record_apply, record_commit, record_verification


def test_committed_recovery_requires_verified_success() -> None:
    source = _source_transaction("commit")
    attempt = create_recovery_attempt(original_transaction_id=source.transaction_id, original_trace_id=source.trace_id)
    attempt = record_recovery_preflight(attempt, {"ok": True})
    tx = create_recovery_transaction(
        attempt=attempt,
        task_id="task-recovery-commit",
        step_id="step-recovery-commit",
        trace_id="trace-recovery-commit",
        authority_source="execution_gateway",
        surface="recovery_apply",
        affected_files=["workspace/shared/recovery-commit.txt"],
    )
    attempt = record_recovery_apply(attempt, {"ok": True}, transaction=tx)
    attempt = record_recovery_verify(attempt, {"ok": True, "verification_ok": True})
    attempt = record_recovery_commit(attempt, {"ok": True, "committed": True})

    assert attempt.state.value == "committed"
    assert assert_recovery_terminal_state(attempt) is True


def test_rolled_back_recovery_requires_rollback_evidence() -> None:
    attempt = create_recovery_attempt(original_transaction_id="runtime_tx:rollback-contract")
    attempt = record_recovery_preflight(attempt, {"ok": True})
    attempt = record_recovery_rollback(attempt, {"ok": True, "rollback_applied": True, "backup": "backup.txt"})

    assert attempt.state.value == "rolled_back"
    assert assert_recovery_terminal_state(attempt) is True


def test_failed_terminal_records_reason() -> None:
    attempt = create_recovery_attempt(original_transaction_id="runtime_tx:failed-contract")
    attempt = record_recovery_terminal_failure(attempt, "strategy_exhausted")

    assert attempt.failure_result["reason"] == "strategy_exhausted"
    assert assert_recovery_terminal_state(attempt) is True


def test_requires_human_review_stops_retry_loop() -> None:
    attempt = create_recovery_attempt(original_transaction_id="runtime_tx:human-review", max_retries=5)
    attempt = record_recovery_requires_human_review(attempt, "unsafe_recovery")
    decision = build_recovery_decision(attempt)

    assert decision.requires_human_review is True
    assert decision.retry_allowed is False
    assert assert_recovery_terminal_state(attempt) is True


def test_recovery_result_is_queryable_by_original_transaction_id() -> None:
    original_id = "runtime_tx:queryable-source"
    attempt = create_recovery_attempt(original_transaction_id=original_id)

    assert list_recovery_attempts(original_transaction_id=original_id)[-1].recovery_attempt_id == attempt.recovery_attempt_id


def test_recovery_replay_preserves_lineage() -> None:
    source = _source_transaction("replay-lineage")
    attempt = create_recovery_attempt(
        original_transaction_id=source.transaction_id,
        original_trace_id=source.trace_id,
        replay_run_id="replay_run:lineage",
        recovery_source="recovery:replay",
    )
    tx = create_recovery_transaction(
        attempt=attempt,
        task_id="task-replay-lineage",
        step_id="step-replay-lineage",
        trace_id="trace-replay-lineage",
        authority_source="execution_gateway",
        surface="recovery_apply",
        affected_files=["workspace/shared/replay-lineage.txt"],
    )

    assert tx.original_transaction_id == source.transaction_id
    assert tx.original_trace_id == source.trace_id
    assert tx.recovery_source == "recovery:replay"
    assert "replay_run:lineage" in tx.replay_refs


def test_source_transaction_remains_immutable() -> None:
    source = _source_transaction("immutable")
    before = source.to_dict()
    attempt = create_recovery_attempt(original_transaction_id=source.transaction_id, original_trace_id=source.trace_id)
    create_recovery_transaction(
        attempt=attempt,
        task_id="task-immutable-recovery",
        step_id="step-immutable-recovery",
        trace_id="trace-immutable-recovery",
        authority_source="execution_gateway",
        surface="recovery_apply",
        affected_files=["workspace/shared/immutable-recovery.txt"],
    )

    assert get_transaction(source.transaction_id).to_dict() == before
    assert assert_recovery_does_not_overwrite_source_transaction(attempt) is True


def test_no_infinite_retrying_after_strategy_exhaustion() -> None:
    attempt = create_recovery_attempt(original_transaction_id="runtime_tx:exhausted", max_retries=1)
    attempt = record_recovery_terminal_failure(attempt, "strategy_exhausted")
    decision = build_recovery_decision(attempt)

    assert decision.state.value == "failed_terminal"
    assert decision.retry_allowed is False


def _source_transaction(suffix: str):
    return create_transaction(
        task_id=f"task-{suffix}",
        step_id=f"step-{suffix}",
        trace_id=f"trace-{suffix}",
        authority_source="execution_gateway",
        surface="write_file",
        affected_files=[f"workspace/shared/{suffix}.txt"],
    )
