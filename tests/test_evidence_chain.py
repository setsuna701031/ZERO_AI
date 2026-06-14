from core.evidence import EvidenceChain, EvidenceRecord, EvidenceValidator


def test_evidence_chain_counts_validation_states() -> None:
    pending = EvidenceRecord("e-p", "goal-1", "sub-1", "tool", "pending", "now")
    validated = EvidenceValidator().validate(
        EvidenceRecord("e-v", "goal-1", "sub-1", "tool", "validated", "now"),
    )
    rejected = EvidenceValidator().reject(
        EvidenceRecord("e-r", "goal-1", "sub-1", "tool", "rejected", "now"),
    )
    chain = EvidenceChain.from_records("goal-1", [pending, validated, rejected], subgoal_id="sub-1")
    assert chain.evidence_ids == ["e-p", "e-v", "e-r"]
    assert chain.validated_evidence_ids == ["e-v"]
    assert chain.validation_summary == {"validated": 1, "rejected": 1, "pending": 1}
    assert chain.has_validated_evidence is True
    assert chain.rejected_count == 1
    assert chain.pending_count == 1
