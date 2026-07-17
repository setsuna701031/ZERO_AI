from pathlib import Path

from core.memory import (
    DecisionMemory,
    EngineeringMemory,
    IssueMemory,
    MemoryQuery,
    MemoryRepository,
    TaskMemory,
)


def test_memory_query_lookups_are_deterministic_filters(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)
    repository.append(
        TaskMemory("task-1", "Build memory", "plan-1", "2026-06-09T01:00:00Z", None, "running")
    )
    repository.append(
        DecisionMemory(
            "decision-1",
            {"state": "blocked", "task_id": "task-1"},
            "resume",
            "approved",
            timestamp="2026-06-09T02:00:00Z",
        )
    )
    repository.append(
        IssueMemory(
            "issue-1",
            "ownership drift",
            "duplicate owner",
            "restore owner",
            "task-1",
            status="reported",
            timestamp="2026-06-09T03:00:00Z",
        )
    )
    repository.append(
        EngineeringMemory(
            "event-1",
            "AER Core Seal Snapshot",
            "Major engineering seal",
            timestamp="2026-06-09T04:00:00Z",
        )
    )
    query = MemoryQuery(repository)

    assert query.find_task_history("task-1")[0]["task_id"] == "task-1"
    assert query.find_previous_decisions("task-1", decision="resume")[0]["decision_id"] == "decision-1"
    assert query.find_related_issues("task-1", text="ownership")[0]["issue_id"] == "issue-1"
    assert query.find_engineering_events(text="seal")[0]["event_id"] == "event-1"
    assert query.find_related_issues("other-task") == []
