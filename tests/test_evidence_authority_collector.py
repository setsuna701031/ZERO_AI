from __future__ import annotations

from core.evidence.evidence_collector import EvidenceCollector
from core.evidence.evidence_contract import EvidenceContract


def _contract() -> EvidenceContract:
    return EvidenceContract(
        plan_id="plan_a",
        goal_id="goal_a",
        subgoal_id="subgoal_a",
        reason="evidence_required_for_goal_completion",
    )


def test_collector_creates_pending_evidence_only() -> None:
    record = EvidenceCollector().collect(
        _contract(),
        source="runtime_result",
        summary={"ok": True},
        timestamp="2026-01-01T00:00:00+00:00",
    )

    assert record.goal_id == "goal_a"
    assert record.subgoal_id == "subgoal_a"
    assert record.source == "runtime_result"
    assert record.summary == {"ok": True}
    assert record.validation_state == "pending"
    assert record.evidence_id.startswith("evidence:")



def test_collector_does_not_validate_or_persist() -> None:
    collector = EvidenceCollector()
    record = collector.collect(
        _contract(),
        source="runtime_result",
        summary="pending proof",
        timestamp="2026-01-01T00:00:00+00:00",
    )

    assert record.validation_state == "pending"
    assert not hasattr(collector, "validate")
    assert not hasattr(collector, "add_record")
    assert not hasattr(collector, "register_evidence")
    assert not hasattr(collector, "complete_goal")
