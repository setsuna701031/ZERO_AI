from __future__ import annotations

import pytest

from core.runtime.snapshot_loader.runtime_seal import (

    build_runtime_seal,
    build_runtime_seal_summary,
    verify_runtime_seal,
)
pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



def test_build_runtime_seal_contract() -> None:
    seal = build_runtime_seal(
        seal_id="seal-1",
    )

    assert seal["seal_id"] == "seal-1"
    assert seal["runtime_seal"] == "snapshot_loader_runtime_seal"

    assert seal["sealed"] is True
    assert seal["governance_integrity"] is True
    assert seal["audit_integrity"] is True
    assert seal["approval_integrity"] is True
    assert seal["replay_integrity"] is True

    assert seal["policy_summary"]["policy_layer"] == (
        "runtime_policy_decision"
    )

    assert seal["approval_summary"]["approval_runtime"] == (
        "snapshot_loader_approval_runtime"
    )

    assert seal["audit_summary"]["audit_runtime"] == (
        "snapshot_loader_audit_runtime"
    )

    assert seal["replay_summary"]["replay_governance"] == (
        "snapshot_loader_replay_governance_envelope"
    )


def test_verify_runtime_seal_accepts_valid_seal() -> None:
    seal = build_runtime_seal(
        seal_id="seal-verify",
    )

    verification = verify_runtime_seal(seal)

    assert verification["sealed"] is True
    assert verification["governance_integrity"] is True
    assert verification["audit_integrity"] is True
    assert verification["approval_integrity"] is True
    assert verification["replay_integrity"] is True
    assert verification["valid"] is True


def test_verify_runtime_seal_detects_invalid_integrity() -> None:
    seal = build_runtime_seal(
        seal_id="seal-invalid",
    )

    seal["audit_integrity"] = False

    verification = verify_runtime_seal(seal)

    assert verification["sealed"] is True
    assert verification["audit_integrity"] is False
    assert verification["valid"] is False


def test_verify_runtime_seal_rejects_non_mapping() -> None:
    with pytest.raises(TypeError):
        verify_runtime_seal(["not", "a", "mapping"])  # type: ignore[arg-type]


def test_runtime_seal_summary_contract() -> None:
    summary = build_runtime_seal_summary()

    assert summary["runtime_seal_layer"] == (
        "snapshot_loader_runtime_seal"
    )

    assert summary["seal"]["sealed"] is True
    assert summary["verification"]["valid"] is True
    assert summary["verification"]["governance_integrity"] is True
    assert summary["verification"]["audit_integrity"] is True
    assert summary["verification"]["approval_integrity"] is True
    assert summary["verification"]["replay_integrity"] is True