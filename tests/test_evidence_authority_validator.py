from __future__ import annotations

from core.evidence.evidence_record import EvidenceRecord
from core.evidence.evidence_validator import EvidenceValidator


def _pending_record() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="evidence_a",
        goal_id="goal_a",
        subgoal_id="subgoal_a",
        source="runtime_result",
        summary={"ok": True},
        timestamp="2026-01-01T00:00:00+00:00",
        validation_state="pending",
    )


def test_validator_returns_validated_or_rejected_copy_only() -> None:
    record = _pending_record()
    validator = EvidenceValidator()

    accepted = validator.validate(record)
    rejected = validator.reject(record)

    assert record.validation_state == "pending"
    assert accepted.validation_state == "validated"
    assert rejected.validation_state == "rejected"
    assert accepted.evidence_id == record.evidence_id
    assert rejected.evidence_id == record.evidence_id


def test_validator_has_no_persistence_or_goal_authority() -> None:
    validator = EvidenceValidator()

    assert not hasattr(validator, "add_record")
    assert not hasattr(validator, "save")
    assert not hasattr(validator, "register_evidence")
    assert not hasattr(validator, "complete_goal")
    assert not hasattr(validator, "update_goal")
