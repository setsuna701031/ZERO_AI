from core.memory import MemoryType, TaskMemory


def test_task_memory_contract_is_serializable_and_immutable() -> None:
    memory = TaskMemory(
        task_id="task-1",
        goal="Build memory",
        plan_id="plan-1",
        start_time="2026-06-09T01:00:00Z",
        end_time="2026-06-09T02:00:00Z",
        result={"status": "completed"},
        evidence_refs=["evidence-1"],
    )

    record = memory.to_dict()

    assert memory.memory_type is MemoryType.TASK
    assert record["record_id"] == "task-1"
    assert record["timestamp"] == "2026-06-09T02:00:00Z"
    assert TaskMemory.from_mapping(record).to_dict() == record
