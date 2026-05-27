from __future__ import annotations

from dataclasses import replace

from core.runtime.runtime_constitution_freeze import (
    RuntimeInvariant,
    assert_authority_invariant,
    assert_evidence_invariant,
    assert_recovery_invariant,
    assert_replay_invariant,
    assert_surface_invariant,
    assert_transaction_invariant,
    create_constitution_snapshot,
)
from core.runtime.runtime_recovery_freeze import create_recovery_attempt
from core.runtime.runtime_replay_freeze import replay_read_only
from core.runtime.runtime_transaction_registry import create_transaction


def test_anonymous_mutation_invariant() -> None:
    try:
        assert_authority_invariant({}, surface="write_file", validation={"ok": True})
    except AssertionError as exc:
        assert "anonymous mutation" in str(exc)
    else:
        raise AssertionError("anonymous mutation should violate constitution")


def test_review_context_not_authority_invariant() -> None:
    try:
        assert_authority_invariant({"review_context": {"ok": True}}, surface="write_file", validation={"ok": True})
    except AssertionError as exc:
        assert "context is not authority" in str(exc)
    else:
        raise AssertionError("review context should not grant authority")


def test_replay_context_not_authority_invariant() -> None:
    try:
        assert_authority_invariant({"replay_context": {"run": "r"}}, surface="replay_mutation", validation={"ok": True})
    except AssertionError as exc:
        assert "context is not authority" in str(exc)
    else:
        raise AssertionError("replay context should not grant authority")


def test_read_only_replay_invariant() -> None:
    assert_surface_invariant("replay_read") is True
    try:
        assert_replay_invariant({"mode": "read_only", "mutation_attempted": True})
    except AssertionError as exc:
        assert "cannot mutate" in str(exc)
    else:
        raise AssertionError("read-only replay mutation should violate constitution")


def test_committed_requires_verified_success_invariant() -> None:
    try:
        assert_transaction_invariant(
            {
                "transaction_id": "runtime_tx:bad",
                "state": "committed",
                "state_history": ["proposed", "preflight", "approved", "applied", "committed"],
                "verification_result": {"ok": False},
            }
        )
    except AssertionError as exc:
        assert "verified success" in str(exc)
    else:
        raise AssertionError("commit without verify should violate constitution")


def test_rollback_evidence_invariant() -> None:
    try:
        assert_transaction_invariant({"transaction_id": "runtime_tx:bad", "state": "rolled_back", "state_history": ["proposed", "rolled_back"]})
    except AssertionError as exc:
        assert "rollback evidence" in str(exc)
    else:
        raise AssertionError("rollback without evidence should violate constitution")


def test_evidence_non_authority_invariant() -> None:
    try:
        assert_evidence_invariant({"evidence_id": "e", "authority_granted": True})
    except AssertionError as exc:
        assert "grant authority" in str(exc)
    else:
        raise AssertionError("evidence authority escalation should violate constitution")


def test_transaction_immutability_invariant() -> None:
    tx = create_transaction(
        task_id="task-immutability",
        step_id="step-immutability",
        trace_id="trace-immutability",
        authority_source="execution_gateway",
        surface="write_file",
        affected_files=["workspace/shared/immutability.txt"],
    )
    mutated = replace(tx, original_transaction_id=tx.transaction_id)
    try:
        assert_transaction_invariant(mutated)
    except AssertionError as exc:
        assert "immutable" in str(exc)
    else:
        raise AssertionError("source transaction reuse should violate constitution")


def test_replay_digest_determinism_invariant() -> None:
    first = replay_read_only([{"event_id": "r", "sequence": 1, "surface": "replay_read", "timestamp": "old"}])
    second = replay_read_only([{"event_id": "r", "sequence": 1, "surface": "replay_read", "timestamp": "new"}])

    assert assert_replay_invariant(first, second=second) is True


def test_recovery_retry_bounded_invariant() -> None:
    attempt = create_recovery_attempt(original_transaction_id="runtime_tx:retry-bounded", max_retries=0)
    attempt = replace(attempt, retry_count=1)
    try:
        assert_recovery_invariant(attempt)
    except AssertionError as exc:
        assert "retry count exceeded" in str(exc)
    else:
        raise AssertionError("unbounded retry should violate constitution")


def test_invariant_snapshot_queryable() -> None:
    snapshot = create_constitution_snapshot(violations=())

    names = {item.invariant for item in snapshot.invariant_snapshots}
    assert RuntimeInvariant.EVIDENCE_CANNOT_GRANT_AUTHORITY in names
    assert snapshot.ok is True
