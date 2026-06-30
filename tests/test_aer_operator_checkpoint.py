from __future__ import annotations

import json

from core.runtime.aer_operator_checkpoint import (
    AER_OPERATOR_CHECKPOINT_CONTRACT,
    CHECKPOINT_REQUIRED_FIELDS,
    build_operator_checkpoint,
    compute_checkpoint_integrity_hash,
    deserialize_operator_checkpoint,
    serialize_operator_checkpoint,
    validate_operator_checkpoint,
)
from core.runtime.aer_operator_lifecycle import AER_OPERATOR_LIFECYCLE_CONTRACT


def test_build_operator_checkpoint_contains_required_fields() -> None:
    payload = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-80",
    )

    assert payload["contract"] == AER_OPERATOR_CHECKPOINT_CONTRACT
    assert payload["lifecycle_contract"] == AER_OPERATOR_LIFECYCLE_CONTRACT

    for field in CHECKPOINT_REQUIRED_FIELDS:
        assert field in payload


def test_validate_operator_checkpoint_accepts_valid_payload() -> None:
    payload = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-80",
        phase="checkpointed",
        completed_phases=("initialized", "admitted", "running"),
        pending_phases=("resumed",),
        metadata={"note": "model only"},
    )

    result = validate_operator_checkpoint(payload)

    assert result["ok"] is True
    assert result["errors"] == []


def test_validate_operator_checkpoint_rejects_non_dict_payload() -> None:
    result = validate_operator_checkpoint(None)

    assert result["ok"] is False
    assert "payload must be a dict" in result["errors"]


def test_validate_operator_checkpoint_rejects_missing_identity_fields() -> None:
    payload = build_operator_checkpoint(
        checkpoint_id="",
        operator_session_id="",
        package_id="",
    )

    result = validate_operator_checkpoint(payload)

    assert result["ok"] is False
    assert "checkpoint_id is required" in result["errors"]
    assert "operator_session_id is required" in result["errors"]
    assert "package_id is required" in result["errors"]


def test_validate_operator_checkpoint_rejects_invalid_contracts() -> None:
    payload = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-80",
    )
    payload["contract"] = "wrong.contract"
    payload["lifecycle_contract"] = "wrong.lifecycle"
    payload["integrity_hash"] = compute_checkpoint_integrity_hash(payload)

    result = validate_operator_checkpoint(payload)

    assert result["ok"] is False
    assert "invalid contract" in result["errors"]
    assert "invalid lifecycle_contract" in result["errors"]


def test_validate_operator_checkpoint_rejects_invalid_phase() -> None:
    payload = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-80",
    )
    payload["phase"] = "not-a-phase"
    payload["integrity_hash"] = compute_checkpoint_integrity_hash(payload)

    result = validate_operator_checkpoint(payload)

    assert result["ok"] is False
    assert "invalid phase: not-a-phase" in result["errors"]


def test_validate_operator_checkpoint_rejects_invalid_phase_lists() -> None:
    payload = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-80",
    )
    payload["completed_phases"] = ["initialized", "bad-phase"]
    payload["pending_phases"] = ["running", "bad-pending"]
    payload["integrity_hash"] = compute_checkpoint_integrity_hash(payload)

    result = validate_operator_checkpoint(payload)

    assert result["ok"] is False
    assert "invalid completed_phases item: bad-phase" in result["errors"]
    assert "invalid pending_phases item: bad-pending" in result["errors"]


def test_validate_operator_checkpoint_rejects_invalid_failed_phase() -> None:
    payload = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-80",
        failed_phase="failed",
    )
    payload["failed_phase"] = "not-a-phase"
    payload["integrity_hash"] = compute_checkpoint_integrity_hash(payload)

    result = validate_operator_checkpoint(payload)

    assert result["ok"] is False
    assert "invalid failed_phase: not-a-phase" in result["errors"]


def test_validate_operator_checkpoint_rejects_non_dict_metadata() -> None:
    payload = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-80",
    )
    payload["metadata"] = []
    payload["integrity_hash"] = compute_checkpoint_integrity_hash(payload)

    result = validate_operator_checkpoint(payload)

    assert result["ok"] is False
    assert "metadata must be a dict" in result["errors"]


def test_validate_operator_checkpoint_rejects_integrity_hash_mismatch() -> None:
    payload = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-80",
    )
    payload["package_id"] = "mutated-package"

    result = validate_operator_checkpoint(payload)

    assert result["ok"] is False
    assert "integrity_hash mismatch" in result["errors"]


def test_checkpoint_serialization_round_trip_is_stable() -> None:
    payload = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-80",
        phase="checkpointed",
        completed_phases=("initialized", "admitted"),
        pending_phases=("running",),
    )

    text = serialize_operator_checkpoint(payload)
    decoded = deserialize_operator_checkpoint(text)

    assert decoded == payload
    assert json.loads(text) == payload
    assert validate_operator_checkpoint(decoded)["ok"] is True


def test_compute_checkpoint_integrity_hash_ignores_integrity_hash_field() -> None:
    payload = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-80",
    )
    first = compute_checkpoint_integrity_hash(payload)
    payload["integrity_hash"] = "changed"
    second = compute_checkpoint_integrity_hash(payload)

    assert first == second