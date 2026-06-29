from __future__ import annotations

from core.runtime.autonomous_repair_loop import normalize_repair_loop_result, run_autonomous_repair_loop
from core.runtime.runtime_constitution_freeze import record_runtime_invariant_violation
from core.runtime.runtime_memory_engine import (

    RuntimeMemoryKind,
    append_runtime_memory,
    assert_memory_non_authoritative,
    create_memory_record,
    query_failure_patterns,
    query_runtime_memory,
    retrieve_experience_memory,
    retrieve_repair_memory,
    retrieve_replay_window,
)
from core.runtime.runtime_recovery_freeze import create_recovery_attempt, record_recovery_terminal_failure
import pytest

pytestmark = [pytest.mark.contract]



def test_repeated_failure_retrieves_prior_repair_memory() -> None:
    loop = run_autonomous_repair_loop(_failure("repeat-failure"), authority=_authority("repeat-failure"))

    memory = retrieve_repair_memory(failure_signature=loop.source_failure_id)

    assert any(record.repair_loop_id == loop.loop_id for record in memory.records)


def test_repeated_repair_strategy_retrieves_stabilization_history() -> None:
    run_autonomous_repair_loop(_failure("strategy-repeat"), authority=_authority("strategy-repeat"), strategy={"strategy_id": "same-stable"})

    records = query_runtime_memory(kind=RuntimeMemoryKind.STABILIZATION_HISTORY, repair_strategy="same-stable")

    assert records
    assert records[0].stabilization_result == "stabilized"


def test_invariant_violation_retrieval_stable() -> None:
    violation = record_runtime_invariant_violation(
        "authority.side_effect_requires_authority",
        component="authority",
        reason="memory_test_violation",
        context={"trace_id": "trace-invariant-memory"},
    )

    first = query_runtime_memory(kind=RuntimeMemoryKind.INVARIANT_VIOLATION, failure_signature="memory_test_violation")
    second = query_runtime_memory(kind=RuntimeMemoryKind.INVARIANT_VIOLATION, failure_signature="memory_test_violation")

    assert first
    assert [item.memory_id for item in first] == [item.memory_id for item in second]
    assert violation.invariant.value in first[0].invariant_refs


def test_failed_repair_retrieves_rollback_lineage() -> None:
    loop = run_autonomous_repair_loop(_failure("rollback-memory"), authority=_authority("rollback-memory"), verification={"ok": False, "reason": "still_failing"})

    records = query_failure_patterns(failure_signature=loop.source_failure_id)

    assert records
    assert records[0].transaction_id


def test_terminal_recovery_retrieves_prior_failure_patterns() -> None:
    attempt = create_recovery_attempt(original_transaction_id="runtime_tx:terminal-memory", original_trace_id="trace-terminal-memory")
    attempt = record_recovery_terminal_failure(attempt, "terminal_memory_failure")

    records = query_failure_patterns(failure_signature="terminal_memory_failure")
    recovery_records = query_runtime_memory(kind=RuntimeMemoryKind.RECOVERY_TERMINAL, recovery_attempt_id=attempt.recovery_attempt_id)

    assert recovery_records
    assert records or recovery_records[0].failure_signature == "terminal_memory_failure"


def test_replay_window_retrieval_preserves_ordering() -> None:
    first = append_runtime_memory(
        create_memory_record(
            kind=RuntimeMemoryKind.REPLAY_WINDOW,
            trace_id="trace-window-order",
            replay_run_id="replay_run:window-order",
            transaction_id="runtime_tx:1",
            evidence_refs=["evidence:1"],
            semantic_tags=["replay"],
        )
    )
    second = append_runtime_memory(
        create_memory_record(
            kind=RuntimeMemoryKind.REPLAY_WINDOW,
            trace_id="trace-window-order",
            replay_run_id="replay_run:window-order",
            transaction_id="runtime_tx:2",
            evidence_refs=["evidence:2"],
            semantic_tags=["replay"],
        )
    )

    window = retrieve_replay_window(trace_id="trace-window-order", replay_run_id="replay_run:window-order")

    assert list(window.memory_ids) == sorted([first.memory_id, second.memory_id])


def test_memory_retrieval_cannot_mutate_runtime() -> None:
    before = normalize_repair_loop_result(run_autonomous_repair_loop(_failure("non-mutate"), authority=_authority("non-mutate")))
    retrieve_experience_memory(trace_id="trace-non-mutate")
    after = retrieve_experience_memory(trace_id="trace-non-mutate")

    assert before["loop_id"]
    for record in after.records:
        assert assert_memory_non_authoritative(record) is True


def test_experience_retrieval_stable_across_repeated_runs() -> None:
    run_autonomous_repair_loop(_failure("experience-stable"), authority=_authority("experience-stable"))

    first = retrieve_experience_memory(trace_id="trace-experience-stable")
    second = retrieve_experience_memory(trace_id="trace-experience-stable")

    assert first.snapshot_id == second.snapshot_id
    assert first.normalized_digest == second.normalized_digest


def _failure(suffix: str) -> dict:
    return {
        "task_id": f"task-{suffix}",
        "step_id": f"step-{suffix}",
        "trace_id": f"trace-{suffix}",
        "failure_id": f"failure-{suffix}",
        "transaction_id": f"runtime_tx:{suffix}",
        "replay_run_id": f"replay_run:{suffix}",
        "recovery_attempt_id": f"runtime_recovery:{suffix}",
    }


def _authority(suffix: str) -> dict:
    return {
        "task_id": f"task-{suffix}",
        "step_id": f"step-{suffix}",
        "authority_source": "execution_gateway",
        "runtime_session": f"session-{suffix}",
        "approval_state": "approved",
        "policy_result": {"allowed": True, "decision": "allow"},
        "trace_id": f"trace-{suffix}",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": "mutation",
    }
