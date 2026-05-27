from __future__ import annotations

from core.runtime.runtime_burnin_runner import (
    assert_burnin_stable,
    run_evidence_burnin,
    run_recovery_burnin,
    run_replay_burnin,
    run_runtime_burnin,
    run_transaction_burnin,
)
from core.runtime.runtime_constitution_freeze import (
    assert_runtime_constitution_integrity,
    create_constitution_snapshot,
    normalize_constitution_snapshot,
)


def test_replay_digest_stable_across_repeated_runs() -> None:
    result = run_replay_burnin(iterations=4)

    assert result["ok"] is True
    assert result["replay_drift"] is False
    assert result["digest"]


def test_transaction_serialization_stable() -> None:
    result = run_transaction_burnin(iterations=4)

    assert result["ok"] is True
    assert result["lineage_corruption"] is False


def test_evidence_snapshot_stable() -> None:
    result = run_evidence_burnin(iterations=4)

    assert result["ok"] is True
    assert result["lineage_corruption"] is False


def test_recovery_terminal_stable() -> None:
    result = run_recovery_burnin(iterations=4)

    assert result["ok"] is True
    assert result["terminal_stable"] is True
    assert result["retry_bounded"] is True


def test_burn_in_detects_invariant_violation() -> None:
    result = run_runtime_burnin(iterations=2, inject_violation=True)

    assert result.ok is False
    assert result.violations


def test_constitution_snapshot_deterministic() -> None:
    first = create_constitution_snapshot(violations=())
    second = create_constitution_snapshot(violations=())

    assert first.snapshot_id == second.snapshot_id
    assert normalize_constitution_snapshot(first) == normalize_constitution_snapshot(second)


def test_invariant_snapshot_queryable() -> None:
    result = run_runtime_burnin(iterations=2)

    snapshots = result.constitution_snapshot.invariant_snapshots
    assert snapshots
    assert {item.component for item in snapshots} >= {"authority", "surface", "transaction", "replay", "recovery", "evidence"}


def test_runtime_constitution_integrity_valid() -> None:
    result = run_runtime_burnin(iterations=2)

    assert assert_runtime_constitution_integrity(result.constitution_snapshot) is True
    assert assert_burnin_stable(result) is True


def test_no_authority_drift_after_repeated_burn_in() -> None:
    first = run_runtime_burnin(iterations=3)
    second = run_runtime_burnin(iterations=3)

    assert first.checks["authority"]["digest"] == second.checks["authority"]["digest"]
    assert first.ok is True
    assert second.ok is True
