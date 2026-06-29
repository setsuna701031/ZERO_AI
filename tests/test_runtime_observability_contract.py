from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from core.runtime.runtime_evidence_freeze import (

    RuntimeEvidenceKind,
    assert_evidence_does_not_grant_authority,
    assert_evidence_is_queryable,
    assert_evidence_lineage_valid,
    create_evidence_record,
    create_evidence_snapshot,
    list_evidence_records,
    normalize_evidence_snapshot,
)
from core.runtime.runtime_transaction_registry import list_transactions
import pytest

pytestmark = [pytest.mark.contract]



def test_evidence_is_queryable_by_task_id() -> None:
    record = _record(task_id="task-query")
    assert record in list_evidence_records(task_id="task-query")


def test_evidence_is_queryable_by_step_id() -> None:
    record = _record(step_id="step-query")
    assert record in list_evidence_records(step_id="step-query")


def test_evidence_is_queryable_by_trace_id() -> None:
    record = _record(trace_id="trace-query")
    assert record in list_evidence_records(trace_id="trace-query")


def test_evidence_is_queryable_by_transaction_id() -> None:
    record = _record(transaction_id="runtime_tx:query")
    assert record in list_evidence_records(transaction_id="runtime_tx:query")


def test_evidence_is_queryable_by_replay_run_id() -> None:
    record = _record(replay_run_id="replay_run:query", kind=RuntimeEvidenceKind.REPLAY)
    assert record in list_evidence_records(replay_run_id="replay_run:query")


def test_evidence_is_queryable_by_recovery_attempt_id() -> None:
    record = _record(recovery_attempt_id="runtime_recovery:query", kind=RuntimeEvidenceKind.RECOVERY)
    assert record in list_evidence_records(recovery_attempt_id="runtime_recovery:query")


def test_evidence_snapshot_serialization_is_stable() -> None:
    first = create_evidence_snapshot([_record(trace_id="trace-stable")])
    second = create_evidence_snapshot([_record(trace_id="trace-stable")])

    assert normalize_evidence_snapshot(first)["normalized_digest"] == normalize_evidence_snapshot(second)["normalized_digest"]


def test_timestamps_are_normalized_out_of_deterministic_digest() -> None:
    record = _record(trace_id="trace-time")
    first = create_evidence_snapshot([record])
    second = replace(first, created_at="2099-01-01T00:00:00Z")

    assert normalize_evidence_snapshot(first) == normalize_evidence_snapshot(second)


def test_evidence_cannot_create_transaction() -> None:
    before = len(list_transactions())
    create_evidence_record(
        kind=RuntimeEvidenceKind.TRANSACTION,
        task_id="task-no-tx",
        transaction_id="runtime_tx:nonexistent",
        state="observed",
    )

    assert len(list_transactions()) == before


def test_evidence_cannot_bypass_authority(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    evidence = _record(trace_id="trace-not-authority")
    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"type": "apply_patch", "target_path": "workspace/shared/nope.txt"},
        context={"evidence": evidence.to_dict()},
    )

    assert assert_evidence_does_not_grant_authority(evidence) is True
    assert result["ok"] is False
    assert result["error"]["type"] == "execution_authority_denied"


def test_evidence_chain_preserves_lineage_order() -> None:
    authority = _record(kind=RuntimeEvidenceKind.AUTHORITY)
    surface = _record(kind=RuntimeEvidenceKind.SURFACE)
    transaction = _record(kind=RuntimeEvidenceKind.TRANSACTION, transaction_id="runtime_tx:lineage")
    replay = _record(kind=RuntimeEvidenceKind.REPLAY, replay_run_id="replay_run:lineage")
    recovery = _record(kind=RuntimeEvidenceKind.RECOVERY, recovery_attempt_id="runtime_recovery:lineage")
    audit = _record(kind=RuntimeEvidenceKind.AUDIT, refs=["audit:lineage"])

    snapshot = create_evidence_snapshot([authority, surface, transaction, replay, recovery, audit])

    assert assert_evidence_lineage_valid(snapshot) is True


def test_evidence_is_queryable_by_id() -> None:
    record = _record(trace_id="trace-id-query")
    assert assert_evidence_is_queryable(record) is True


def _record(
    *,
    kind: RuntimeEvidenceKind = RuntimeEvidenceKind.AUTHORITY,
    task_id: str = "task-observe",
    step_id: str = "step-observe",
    trace_id: str = "trace-observe",
    transaction_id: str = "",
    replay_run_id: str = "",
    recovery_attempt_id: str = "",
    refs: list[str] | None = None,
):
    return create_evidence_record(
        kind=kind,
        task_id=task_id,
        step_id=step_id,
        trace_id=trace_id,
        transaction_id=transaction_id,
        replay_run_id=replay_run_id,
        recovery_attempt_id=recovery_attempt_id,
        authority_source="execution_gateway",
        surface="write_file",
        decision="observed",
        state="observed",
        reason="observability_contract",
        refs=refs or [],
    )
