from __future__ import annotations

from core.runtime.autonomous_repair_loop import (
    AutonomousRepairState,
    assert_repair_loop_bounded,
    apply_repair_action,
    decide_repair_commit_or_rollback,
    diagnose_runtime_failure,
    observe_runtime_failure,
    propose_repair_action,
    resume_after_repair,
    run_autonomous_repair_loop,
    stabilize_repair_loop,
    verify_repair_action,
)
from core.runtime.runtime_evidence_freeze import assert_evidence_does_not_grant_authority
from core.runtime.runtime_transaction_registry import get_transaction


def test_max_attempts_bounds_loop() -> None:
    loop = run_autonomous_repair_loop(_failure(), authority=_authority(), max_attempts=1)

    assert assert_repair_loop_bounded(loop) is True


def test_repeated_same_failed_repair_strategy_triggers_anti_oscillation() -> None:
    loop = observe_runtime_failure(_failure(), max_attempts=1)
    loop = diagnose_runtime_failure(loop)
    loop = propose_repair_action(loop, {"strategy_id": "same_strategy"})
    loop = propose_repair_action(loop, {"strategy_id": "same_strategy"})

    assert loop.final_state is AutonomousRepairState.REQUIRES_HUMAN_REVIEW
    assert loop.terminal is True


def test_invariant_violation_blocks_repair_loop() -> None:
    loop = propose_repair_action(diagnose_runtime_failure(observe_runtime_failure(_failure())))
    blocked = apply_repair_action(loop, authority={})

    assert blocked.final_state is AutonomousRepairState.BLOCKED
    assert blocked.invariant_refs


def test_replay_evidence_does_not_grant_repair_authority() -> None:
    evidence = {"kind": "replay", "replay_run_id": "replay_run:authority", "state": "verified"}

    assert assert_evidence_does_not_grant_authority(evidence) is True
    loop = apply_repair_action(propose_repair_action(diagnose_runtime_failure(observe_runtime_failure(_failure()))), authority={"evidence": evidence})
    assert loop.final_state is AutonomousRepairState.BLOCKED


def test_repair_created_transaction_differs_from_source_transaction() -> None:
    loop = run_autonomous_repair_loop(_failure(), authority=_authority())
    tx = get_transaction(loop.transaction_refs[-1])

    assert tx.transaction_id != loop.source_transaction_id
    assert tx.original_transaction_id == loop.source_transaction_id
    assert tx.repair_loop_id == loop.loop_id


def test_rollback_requires_rollback_evidence() -> None:
    loop = apply_repair_action(propose_repair_action(diagnose_runtime_failure(observe_runtime_failure(_failure()))), authority=_authority())

    result = decide_repair_commit_or_rollback(loop, rollback_evidence={})

    assert result.final_state is AutonomousRepairState.REQUIRES_HUMAN_REVIEW
    assert "transaction.rollback_requires_rollback_evidence" in result.invariant_refs


def test_failed_repair_records_deterministic_failure_reason() -> None:
    first = run_autonomous_repair_loop(_failure(), authority=_authority(), verification={"ok": False, "reason": "still_failing"})
    second = run_autonomous_repair_loop(_failure(), authority=_authority(), verification={"ok": False, "reason": "still_failing"})

    first_reasons = [attempt.reason for attempt in first.attempts if attempt.reason]
    second_reasons = [attempt.reason for attempt in second.attempts if attempt.reason]
    assert first_reasons == second_reasons
    assert "still_failing" in first_reasons


def test_resume_only_allowed_after_verified_commit_or_safe_rollback() -> None:
    loop = propose_repair_action(diagnose_runtime_failure(observe_runtime_failure(_failure())))
    result = resume_after_repair(loop)

    assert result.final_state is AutonomousRepairState.REQUIRES_HUMAN_REVIEW


def test_stabilize_requires_terminal_recovery_or_repair_state() -> None:
    loop = propose_repair_action(diagnose_runtime_failure(observe_runtime_failure(_failure())))
    result = stabilize_repair_loop(loop)

    assert result.final_state is AutonomousRepairState.REQUIRES_HUMAN_REVIEW


def test_no_infinite_retrying_after_strategy_exhaustion() -> None:
    loop = observe_runtime_failure(_failure(), max_attempts=0)
    loop = diagnose_runtime_failure(loop)
    loop = propose_repair_action(loop, {"strategy_id": "exhausted"})

    assert loop.final_state is AutonomousRepairState.REQUIRES_HUMAN_REVIEW
    assert loop.terminal is True


def _failure():
    return {
        "task_id": "task-safety",
        "step_id": "step-safety",
        "trace_id": "trace-safety",
        "failure_id": "failure-safety",
        "transaction_id": "runtime_tx:source-safety",
        "replay_run_id": "replay_run:source-safety",
        "recovery_attempt_id": "runtime_recovery:source-safety",
    }


def _authority():
    return {
        "task_id": "task-safety",
        "step_id": "step-safety",
        "authority_source": "execution_gateway",
        "runtime_session": "session-safety",
        "approval_state": "approved",
        "policy_result": {"allowed": True, "decision": "allow"},
        "trace_id": "trace-safety",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": "mutation",
    }
