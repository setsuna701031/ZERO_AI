from core.evidence import EvidenceRecord, EvidenceValidator


def _record() -> EvidenceRecord:
    return EvidenceRecord("e-1", "goal-1", None, "scanner", "report exists", "2026-06-09T00:00:00Z")


def test_validator_validates_evidence_without_mutating_original() -> None:
    original = _record()
    validated = EvidenceValidator().validate(original)
    assert original.validation_state == "pending"
    assert validated.validation_state == "validated"


def test_validator_rejects_evidence() -> None:
    rejected = EvidenceValidator().reject(_record())
    assert rejected.validation_state == "rejected"


def test_validator_rejects_caller_controlled_accepted_flag() -> None:
    try:
        EvidenceValidator().validate(_record(), accepted=True)
    except TypeError:
        return
    raise AssertionError("caller-controlled accepted flag must not validate evidence")
