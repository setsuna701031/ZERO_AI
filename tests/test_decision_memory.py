import pytest

from core.memory import DecisionMemory, MemoryType


def test_decision_memory_records_reason_without_making_decisions() -> None:
    memory = DecisionMemory(
        decision_id="decision-1",
        context={"state": "blocked"},
        decision="resume",
        reason="operator approved continuation",
        evidence_refs=["evidence-1"],
        timestamp="2026-06-09T03:00:00Z",
    )

    assert memory.memory_type is MemoryType.DECISION
    assert DecisionMemory.from_mapping(memory.to_dict()) == memory


def test_decision_memory_rejects_missing_reason() -> None:
    with pytest.raises(ValueError, match="memory_requires_reason"):
        DecisionMemory(decision_id="decision-1", context={}, decision="resume", reason="")
