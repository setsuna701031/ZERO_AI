from __future__ import annotations

from pathlib import Path

from core.memory.memory_repository import MemoryRepository
from core.memory.task_memory import TaskMemory


def test_canonical_task_memory_is_append_only_record(tmp_path: Path) -> None:
    memory = TaskMemory(
        task_id="test-memory-case",
        goal="verify canonical task memory",
        plan_id="plan-test-memory",
        start_time="2026-06-11T00:00:00Z",
        end_time="2026-06-11T00:01:00Z",
        result={"status": "finished", "message": "memory test finished"},
        evidence_refs=["evidence:test-memory"],
    )
    repository = MemoryRepository(tmp_path)

    saved = repository.append(memory)
    loaded = repository.list_by_task("test-memory-case")

    assert saved["record_id"] == "test-memory-case"
    assert saved["memory_type"] == "task"
    assert loaded == [saved]
    assert loaded[0]["result"]["status"] == "finished"
