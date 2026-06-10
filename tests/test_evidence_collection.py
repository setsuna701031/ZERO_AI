from core.evidence import EvidenceCollector, EvidenceContract


def test_collector_creates_pending_record_without_validation() -> None:
    contract = EvidenceContract("plan-1", "goal-1", "sub-1", "completion evidence", ["report"])
    record = EvidenceCollector().collect(contract, source="artifact_scanner", summary={"artifact": "report"})
    assert record.goal_id == "goal-1"
    assert record.validation_state == "pending"
