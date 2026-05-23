from __future__ import annotations

import pytest

from core.runtime.rollback_verification import (
    RollbackVerificationGate,
    RollbackVerificationGateRejected,
    RollbackVerificationRecord,
    RollbackVerificationVerifier,
    evaluate_rollback_verification_gate,
    enforce_rollback_verification_gate,
)


def _record(result: str, mismatches=None) -> RollbackVerificationRecord:
    return RollbackVerificationRecord(
        rollback_id="rollback-001",
        snapshot_id="snapshot-001",
        plan_id="plan-001",
        execution_order=["a", "b", "c"],
        rollback_order=["c", "b", "a"],
        verification_result=result,
        mismatches=mismatches or [],
        snapshot_fingerprint="snapshot-fingerprint",
        aggregate_status="completed",
        operation_fingerprints={"a": "fa", "b": "fb", "c": "fc"},
        metadata={"source": "test"},
        runtime_args={"mode": "test"},
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_rollback_verification_gate_allows_verified_record() -> None:
    result = evaluate_rollback_verification_gate(
        _record(RollbackVerificationVerifier.VERIFIED),
    )

    assert result.ok is True
    assert result.allowed_to_continue is True
    assert result.runtime_frozen is False
    assert result.verification_result == "verified"
    assert result.to_dict()["record"]["rollback_id"] == "rollback-001"


def test_rollback_verification_gate_freezes_on_mismatch() -> None:
    result = RollbackVerificationGate().evaluate_record(
        _record(
            RollbackVerificationVerifier.MISMATCHED,
            mismatches=[
                {
                    "type": "rollback_order_mismatch",
                    "expected": ["c", "b", "a"],
                    "actual": ["a", "b", "c"],
                }
            ],
        )
    )

    assert result.ok is False
    assert result.allowed_to_continue is False
    assert result.runtime_frozen is True
    assert result.verification_result == "mismatched"
    assert result.mismatches[0]["type"] == "rollback_order_mismatch"


def test_rollback_verification_gate_enforce_raises_on_mismatch() -> None:
    with pytest.raises(RollbackVerificationGateRejected):
        enforce_rollback_verification_gate(
            _record(
                RollbackVerificationVerifier.MISMATCHED,
                mismatches=[{"type": "missing_operation", "operation_id": "b"}],
            )
        )
