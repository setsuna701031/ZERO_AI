from pathlib import Path

from core.adaptive import AdaptiveMemoryContextBuilder, AdaptiveMemoryPolicy, DeviationReport
from core.memory import DecisionMemory, EngineeringMemory, IssueMemory, MemoryRepository


def _report(reason: str = "artifact_missing", observed=None) -> DeviationReport:
    return DeviationReport(
        "task-1",
        "step-1",
        {},
        observed or {},
        True,
        reason,
        "high",
        True,
    )


def _populate(repository: MemoryRepository) -> None:
    repository.append(
        IssueMemory(
            "issue-1",
            "artifact missing report.txt",
            "report writer skipped output",
            "restore report writer",
            "task-1",
            ["ev-issue"],
            "reported",
            "2026-06-09T01:00:00Z",
        )
    )
    repository.append(
        DecisionMemory(
            "decision-1",
            {"task_id": "task-1"},
            "replan",
            "artifact was missing",
            ["ev-decision"],
            "2026-06-09T02:00:00Z",
        )
    )
    repository.append(
        EngineeringMemory(
            "event-1",
            "artifact_missing boundary sealed",
            "Adaptive remains sole decision owner",
            ["ev-event"],
            "2026-06-09T03:00:00Z",
            "task-1",
        )
    )


def test_no_repository_and_empty_repository_return_empty_context(tmp_path: Path) -> None:
    no_repository = AdaptiveMemoryContextBuilder().build(_report())
    empty = AdaptiveMemoryContextBuilder(MemoryRepository(tmp_path)).build(_report())

    assert no_repository.related_issues == []
    assert empty.related_decisions == []
    assert empty.warnings == []


def test_builder_adds_related_memory_without_modifying_report_or_repository(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)
    _populate(repository)
    report = _report()
    report_before = report.to_dict()
    repository_before = repository.storage_path.read_bytes()

    context = AdaptiveMemoryContextBuilder(repository).build(report)

    assert context.related_issues[0].memory_id == "issue-1"
    assert context.related_decisions[0].memory_id == "decision-1"
    assert context.related_engineering_events[0].memory_id == "event-1"
    assert context.evidence_refs == ["ev-issue", "ev-decision", "ev-event"]
    assert report.to_dict() == report_before
    assert repository.storage_path.read_bytes() == repository_before


def test_artifact_missing_can_find_issue_by_missing_artifact_text(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)
    repository.append(
        IssueMemory(
            "issue-similar",
            "report.txt artifact missing",
            "writer omitted output",
            "restore output",
            None,
            status="reported",
        )
    )

    context = AdaptiveMemoryContextBuilder(repository).build(
        _report(observed={"missing_artifacts": ["report.txt"]})
    )

    assert context.related_issues[0].memory_id == "issue-similar"
    assert context.related_issues[0].relevance_reason == "deviation_text_match"


def test_query_failure_returns_empty_context_and_does_not_repair_contract(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)
    repository.storage_path.parent.mkdir(parents=True)
    repository.storage_path.write_text('{"memory_type":"issue","timestamp":"now"}\n', encoding="utf-8")
    before = repository.storage_path.read_bytes()

    context = AdaptiveMemoryContextBuilder(repository).build(_report())

    assert context.related_issues == []
    assert context.warnings[0].startswith("adaptive_memory_context_query_failed:ValueError:")
    assert repository.storage_path.read_bytes() == before


def test_policy_can_disable_memory_types(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)
    _populate(repository)
    policy = AdaptiveMemoryPolicy(
        allow_issue_memory=False,
        allow_decision_memory=False,
        allow_engineering_memory=False,
    )

    context = AdaptiveMemoryContextBuilder(repository, policy=policy).build(_report())

    assert context.related_issues == []
    assert context.related_decisions == []
    assert context.related_engineering_events == []
