from __future__ import annotations

from core.runtime.runtime_memory_engine import (
    RuntimeMemoryKind,
    append_runtime_memory,
    assert_memory_non_authoritative,
    assert_memory_preserves_lineage,
    assert_memory_snapshot_stable,
    build_memory_window,
    create_memory_record,
    query_failure_patterns,
    query_repair_history,
    query_stabilization_history,
    retrieve_repair_memory,
    retrieve_replay_window,
    normalize_memory_snapshot,
    retrieve_experience_memory,
)


def test_memory_record_creation_stable() -> None:
    first = _record()
    second = _record()

    assert first.memory_id == second.memory_id
    assert first.normalized_digest == second.normalized_digest


def test_memory_snapshot_deterministic() -> None:
    record = append_runtime_memory(_record())
    first = retrieve_experience_memory(trace_id=record.trace_id)
    second = retrieve_experience_memory(trace_id=record.trace_id)

    assert first.snapshot_id == second.snapshot_id
    assert normalize_memory_snapshot(first) == normalize_memory_snapshot(second)
    assert assert_memory_snapshot_stable(first, second) is True


def test_replay_window_retrieval_stable() -> None:
    replay = append_runtime_memory(
        create_memory_record(
            kind=RuntimeMemoryKind.REPLAY_WINDOW,
            trace_id="trace-memory-replay",
            replay_run_id="replay_run:memory",
            evidence_refs=["evidence:replay"],
            summary="replay memory",
            semantic_tags=["replay", "window"],
        )
    )

    first = retrieve_replay_window(trace_id="trace-memory-replay", replay_run_id="replay_run:memory")
    second = retrieve_replay_window(trace_id="trace-memory-replay", replay_run_id="replay_run:memory")

    assert first.memory_ids == (replay.memory_id,)
    assert first.normalized_digest == second.normalized_digest


def test_repair_history_retrieval_stable() -> None:
    record = append_runtime_memory(_record(repair_strategy="strategy-memory"))

    first = query_repair_history(repair_strategy="strategy-memory")
    second = query_repair_history(repair_strategy="strategy-memory")

    assert record.memory_id in [item.memory_id for item in first]
    assert [item.memory_id for item in first] == [item.memory_id for item in second]


def test_failure_pattern_retrieval_stable() -> None:
    record = append_runtime_memory(
        create_memory_record(
            kind=RuntimeMemoryKind.FAILURE_PATTERN,
            trace_id="trace-failure-memory",
            transaction_id="runtime_tx:failure-memory",
            evidence_refs=["evidence:failure"],
            failure_signature="syntax_error",
            semantic_tags=["failure"],
        )
    )

    assert query_failure_patterns(failure_signature="syntax_error")[0].memory_id == record.memory_id


def test_stabilization_history_retrieval_stable() -> None:
    record = append_runtime_memory(
        create_memory_record(
            kind=RuntimeMemoryKind.STABILIZATION_HISTORY,
            trace_id="trace-stable-memory",
            repair_loop_id="repair_loop:stable-memory",
            evidence_refs=["evidence:stable"],
            repair_strategy="stable_strategy",
            stabilization_result="stabilized",
            terminal_state="stabilized",
            semantic_tags=["stabilization"],
        )
    )

    assert record.memory_id in [item.memory_id for item in query_stabilization_history(repair_strategy="stable_strategy")]


def test_memory_preserves_lineage_refs() -> None:
    assert assert_memory_preserves_lineage(_record()) is True


def test_memory_cannot_grant_authority() -> None:
    try:
        assert_memory_non_authoritative({"memory_id": "m", "kind": "repair_history", "authority_granted": True})
    except AssertionError as exc:
        assert "authority" in str(exc)
    else:
        raise AssertionError("memory authority escalation should fail")


def test_memory_cannot_create_transaction() -> None:
    try:
        assert_memory_non_authoritative({"memory_id": "m", "kind": "repair_history", "transaction_created": True})
    except AssertionError as exc:
        assert "transaction" in str(exc)
    else:
        raise AssertionError("memory transaction creation should fail")


def test_memory_digest_stable() -> None:
    record = append_runtime_memory(_record())
    snapshot = retrieve_repair_memory(failure_signature=record.failure_signature)

    assert record.normalized_digest
    assert snapshot.normalized_digest


def _record(**overrides):
    payload = {
        "kind": RuntimeMemoryKind.REPAIR_HISTORY,
        "task_id": "task-memory",
        "trace_id": "trace-memory",
        "step_id": "step-memory",
        "transaction_id": "runtime_tx:memory",
        "replay_run_id": "replay_run:memory",
        "recovery_attempt_id": "runtime_recovery:memory",
        "repair_loop_id": "repair_loop:memory",
        "evidence_refs": ["evidence:memory"],
        "invariant_refs": ["invariant:memory"],
        "summary": "memory summary",
        "semantic_tags": ["repair", "memory"],
        "failure_signature": "failure-memory",
        "repair_strategy": "strategy-memory",
        "stabilization_result": "stabilized",
        "terminal_state": "stabilized",
    }
    payload.update(overrides)
    return create_memory_record(**payload)
