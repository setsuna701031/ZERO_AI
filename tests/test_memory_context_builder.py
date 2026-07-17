from pathlib import Path

from core.memory import DecisionMemory, EngineeringMemory, IssueMemory, MemoryRepository, TaskMemory
from core.planning.memory_context import MemoryContextBuilder, PlannerMemoryPolicy


def _populate(repository: MemoryRepository) -> None:
    repository.append(
        TaskMemory("task-1", "Build memory aware planning", "plan-1", "2026-06-09T01:00:00Z", None, "running", ["ev-task"])
    )
    repository.append(
        DecisionMemory(
            "decision-1",
            {"task_id": "task-1"},
            "continue",
            "history supports continuation",
            ["ev-decision"],
            "2026-06-09T02:00:00Z",
        )
    )
    repository.append(
        IssueMemory(
            "issue-1",
            "ownership drift",
            "duplicate owner",
            "restore owner",
            "task-1",
            ["ev-issue"],
            "reported",
            "2026-06-09T03:00:00Z",
        )
    )
    repository.append(
        EngineeringMemory(
            "event-1",
            "Memory Layer v1 sealed",
            "Read-only memory foundation",
            ["ev-event"],
            "2026-06-09T04:00:00Z",
            "task-1",
        )
    )


def test_no_repository_and_empty_repository_return_empty_context(tmp_path: Path) -> None:
    without_repository = MemoryContextBuilder().build(task_id="task-1", goal="goal")
    empty_repository = MemoryContextBuilder(MemoryRepository(tmp_path)).build(task_id="task-1", goal="goal")

    assert without_repository.related_tasks == []
    assert empty_repository.related_decisions == []
    assert empty_repository.warnings == []


def test_builder_adds_related_memory_without_modifying_repository(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)
    _populate(repository)
    before = repository.storage_path.read_bytes()

    context = MemoryContextBuilder(repository).build(task_id="task-1", goal="Build memory aware planning")

    assert context.related_tasks[0].memory_id == "task-1"
    assert context.related_decisions[0].memory_id == "decision-1"
    assert context.related_issues[0].memory_id == "issue-1"
    assert context.related_engineering_events[0].memory_id == "event-1"
    assert context.evidence_refs == ["ev-task", "ev-decision", "ev-issue", "ev-event"]
    assert repository.storage_path.read_bytes() == before


def test_policy_can_exclude_optional_memory_types(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)
    _populate(repository)
    policy = PlannerMemoryPolicy(
        allow_issue_memory=False,
        allow_decision_memory=False,
        allow_engineering_memory=False,
    )

    context = MemoryContextBuilder(repository, policy=policy).build(task_id="task-1", goal="goal")

    assert len(context.related_tasks) == 1
    assert context.related_decisions == []
    assert context.related_issues == []
    assert context.related_engineering_events == []


def test_contract_violation_is_not_repaired_and_returns_warning(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)
    repository.storage_path.parent.mkdir(parents=True)
    repository.storage_path.write_text('{"memory_type":"task","timestamp":"now"}\n', encoding="utf-8")
    before = repository.storage_path.read_bytes()

    context = MemoryContextBuilder(repository).build(task_id="task-1", goal="goal")

    assert context.related_tasks == []
    assert context.warnings[0].startswith("memory_context_query_failed:ValueError:")
    assert repository.storage_path.read_bytes() == before
