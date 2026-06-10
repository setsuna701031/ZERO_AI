from core.memory import IssueMemory, MemoryType


def test_issue_memory_records_non_mainline_issue() -> None:
    memory = IssueMemory(
        issue_id="issue-1",
        title="terminal metadata drift",
        root_cause="writers disagree",
        fix="align metadata writers",
        related_task="task-1",
        evidence_refs=["evidence-1"],
        status="reported",
        timestamp="2026-06-09T04:00:00Z",
    )

    assert memory.memory_type is MemoryType.ISSUE
    assert memory.to_dict()["related_task"] == "task-1"
    assert IssueMemory.from_mapping(memory.to_dict()) == memory
