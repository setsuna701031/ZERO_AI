from core.memory import EngineeringMemory, MemoryType


def test_engineering_memory_records_major_event() -> None:
    memory = EngineeringMemory(
        event_id="event-1",
        title="Runtime State Ownership Seal",
        description="Ownership boundary sealed",
        evidence_refs=["evidence-1"],
        timestamp="2026-06-09T05:00:00Z",
    )

    assert memory.memory_type is MemoryType.ENGINEERING
    assert EngineeringMemory.from_mapping(memory.to_dict()) == memory
