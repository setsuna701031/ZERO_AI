import pytest

from core.evidence import EvidenceRecord


def test_evidence_record_is_created_pending() -> None:
    record = EvidenceRecord("e-1", "goal-1", "sub-1", "tool", {"artifact": "report"}, "2026-06-09T00:00:00Z")
    assert record.validation_state == "pending"
    assert record.to_dict()["summary"]["artifact"] == "report"


def test_evidence_record_rejects_invalid_state() -> None:
    with pytest.raises(ValueError, match="valid_validation_state"):
        EvidenceRecord("e-1", "goal-1", None, "tool", "summary", "now", "trusted")
