from __future__ import annotations

from core.runtime.runtime_memory_engine import (

    RuntimeMemoryKind,
    assert_memory_non_authoritative,
    build_memory_window,
    compact_memory_window,
    create_memory_record,
)
from core.runtime.runtime_memory_index import (
    assert_memory_index_integrity,
    compact_memory_index,
    index_runtime_memory,
    query_memory_by_failure_signature,
    query_memory_by_repair_strategy,
    query_memory_by_semantic_tag,
    query_memory_by_terminal_state,
    query_memory_by_trace,
    query_memory_by_transaction,
)
import pytest

pytestmark = [pytest.mark.contract]



def test_query_by_trace_id() -> None:
    index = index_runtime_memory(_records())

    assert [item.trace_id for item in query_memory_by_trace(index, "trace-index")] == ["trace-index", "trace-index"]


def test_query_by_transaction_id() -> None:
    index = index_runtime_memory(_records())

    assert query_memory_by_transaction(index, "runtime_tx:index")[0].transaction_id == "runtime_tx:index"


def test_query_by_repair_strategy() -> None:
    index = index_runtime_memory(_records())

    assert query_memory_by_repair_strategy(index, "strategy-index")[0].repair_strategy == "strategy-index"


def test_query_by_failure_signature() -> None:
    index = index_runtime_memory(_records())

    assert query_memory_by_failure_signature(index, "failure-index")[0].failure_signature == "failure-index"


def test_query_by_semantic_tag() -> None:
    index = index_runtime_memory(_records())

    assert len(query_memory_by_semantic_tag(index, "repair")) == 1


def test_compacted_memory_preserves_lineage() -> None:
    window = build_memory_window(_records(), trace_id="trace-index")
    compacted = compact_memory_window(window, max_records=1)

    assert compacted.compacted is True
    assert compacted.lineage_refs


def test_compacted_memory_deterministic() -> None:
    first = compact_memory_index(index_runtime_memory(_records()), max_records=1)
    second = compact_memory_index(index_runtime_memory(_records()), max_records=1)

    assert first.index_id == second.index_id
    assert first.normalized_digest == second.normalized_digest


def test_memory_index_integrity_stable() -> None:
    index = index_runtime_memory(_records())

    assert assert_memory_index_integrity(index) is True


def test_replay_window_retrieval_deterministic() -> None:
    first = build_memory_window(_records(), trace_id="trace-index", replay_run_id="replay_run:index")
    second = build_memory_window(_records(), trace_id="trace-index", replay_run_id="replay_run:index")

    assert first.memory_ids == second.memory_ids
    assert first.normalized_digest == second.normalized_digest


def test_memory_retrieval_non_authoritative() -> None:
    record = query_memory_by_terminal_state(index_runtime_memory(_records()), "stabilized")[0]

    assert assert_memory_non_authoritative(record) is True


def _records():
    return [
        create_memory_record(
            kind=RuntimeMemoryKind.REPAIR_HISTORY,
            trace_id="trace-index",
            transaction_id="runtime_tx:index",
            replay_run_id="replay_run:index",
            recovery_attempt_id="runtime_recovery:index",
            repair_loop_id="repair_loop:index",
            evidence_refs=["evidence:index"],
            invariant_refs=["invariant:index"],
            failure_signature="failure-index",
            repair_strategy="strategy-index",
            terminal_state="stabilized",
            semantic_tags=["repair", "experience"],
        ),
        create_memory_record(
            kind=RuntimeMemoryKind.FAILURE_PATTERN,
            trace_id="trace-index",
            transaction_id="runtime_tx:failure-index",
            evidence_refs=["evidence:failure-index"],
            failure_signature="failure-index",
            terminal_state="failed_terminal",
            semantic_tags=["failure"],
        ),
    ]
