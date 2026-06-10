from core.evidence import EvidenceRecord, EvidenceValidator


def _record() -> EvidenceRecord:
    return EvidenceRecord("e-1", "goal-1", None, "scanner", "report exists", "2026-06-09T00:00:00Z")


def test_validator_validates_evidence_without_mutating_original() -> None:
    original = _record()
    validated = EvidenceValidator().validate(original, accepted=True)
    assert original.validation_state == "pending"
    assert validated.validation_state == "validated"


def test_validator_rejects_evidence() -> None:
    rejected = EvidenceValidator().validate(_record(), accepted=False)
    assert rejected.validation_state == "rejected"
