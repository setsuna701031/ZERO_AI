from __future__ import annotations

from core.runtime.runtime_memory_engine import (
    RuntimeMemoryKind,
    append_runtime_memory,
    compact_memory_window,
    create_memory_record,
    query_runtime_memory,
    retrieve_replay_window,
)
from core.runtime.runtime_prediction_engine import (
    assert_prediction_non_authoritative,
    normalize_prediction_result,
    predict_repair_outcome,
    predict_replay_divergence,
    predict_rollback_risk,
    predict_stabilization_probability,
    predict_mutation_impact,
)


def test_repeated_failure_prediction_retrieves_prior_failure_memory() -> None:
    record = _memory(RuntimeMemoryKind.FAILURE_PATTERN, failure_signature="failure-memory-contract")
    result = predict_mutation_impact(_context(failure_signature="failure-memory-contract"))

    assert record.memory_id in result.memory_refs


def test_repair_prediction_retrieves_stabilization_history() -> None:
    record = _memory(RuntimeMemoryKind.STABILIZATION_HISTORY, repair_strategy="strategy-memory-contract", stabilization_result="stabilized")
    result = predict_repair_outcome(_context(repair_strategy="strategy-memory-contract"))

    assert record.memory_id in result.memory_refs


def test_rollback_prediction_retrieves_rollback_lineage() -> None:
    record = _memory(RuntimeMemoryKind.RECOVERY_TERMINAL, terminal_state="rolled_back", semantic_tags=["rollback"])
    result = predict_rollback_risk(_context(source_recovery_attempt_id="runtime_recovery:memory-contract"))

    assert record.memory_id in result.memory_refs


def test_replay_divergence_prediction_retrieves_replay_window_memory() -> None:
    record = _memory(RuntimeMemoryKind.REPLAY_WINDOW, replay_run_id="replay_run:memory-contract")
    result = predict_replay_divergence(_context(source_replay_run_id="replay_run:memory-contract"))

    assert record.memory_id in result.memory_refs


def test_memory_assisted_prediction_remains_non_authoritative() -> None:
    result = predict_repair_outcome(_context())

    assert assert_prediction_non_authoritative(result) is True
    assert result.authoritative is False


def test_prediction_output_stable_across_repeated_memory_retrieval() -> None:
    _memory(RuntimeMemoryKind.REPAIR_HISTORY)
    first = predict_repair_outcome(_context())
    second = predict_repair_outcome(_context())

    assert normalize_prediction_result(first) == normalize_prediction_result(second)


def test_compacted_memory_still_supports_prediction() -> None:
    record = _memory(RuntimeMemoryKind.REPLAY_WINDOW, replay_run_id="replay_run:memory-contract-compact")
    compacted = compact_memory_window(retrieve_replay_window(trace_id="trace-memory-contract", replay_run_id="replay_run:memory-contract-compact"))
    result = predict_replay_divergence(_context(source_replay_run_id="replay_run:memory-contract-compact", source_memory_ids=compacted.memory_ids))

    assert record.memory_id in result.memory_refs


def test_prediction_does_not_mutate_memory_index() -> None:
    _memory(RuntimeMemoryKind.REPAIR_HISTORY)
    before = tuple(record.memory_id for record in query_runtime_memory(trace_id="trace-memory-contract"))
    predict_stabilization_probability(_context())
    after = tuple(record.memory_id for record in query_runtime_memory(trace_id="trace-memory-contract"))

    assert before == after


def _memory(kind: RuntimeMemoryKind, **overrides):
    payload = {
        "kind": kind,
        "task_id": "task-memory-contract",
        "step_id": "step-memory-contract",
        "trace_id": "trace-memory-contract",
        "transaction_id": "runtime_tx:memory-contract",
        "replay_run_id": "replay_run:memory-contract",
        "recovery_attempt_id": "runtime_recovery:memory-contract",
        "repair_loop_id": "repair_loop:memory-contract",
        "evidence_refs": ["runtime_evidence:memory-contract"],
        "failure_signature": "failure-memory-contract",
        "repair_strategy": "strategy-memory-contract",
        "semantic_tags": ["memory", kind.value],
    }
    payload.update(overrides)
    return append_runtime_memory(create_memory_record(**payload))


def _context(**overrides):
    payload = {
        "task_id": "task-memory-contract",
        "step_id": "step-memory-contract",
        "trace_id": "trace-memory-contract",
        "source_transaction_id": "runtime_tx:memory-contract",
        "source_replay_run_id": "replay_run:memory-contract",
        "source_recovery_attempt_id": "runtime_recovery:memory-contract",
        "source_repair_loop_id": "repair_loop:memory-contract",
        "failure_signature": "failure-memory-contract",
        "repair_strategy": "strategy-memory-contract",
    }
    payload.update(overrides)
    return payload
