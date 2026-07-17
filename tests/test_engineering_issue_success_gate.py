from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_goal_runner import EngineeringGoalRunner
from core.tasks.engineering_issue_reporter import EngineeringIssueReporter
from core.tasks.engineering_issue_summary import apply_engineering_issue_summary


REPO_ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_FILES = [
    REPO_ROOT / "core/tasks/engineering_runtime_orchestrator.py",
    REPO_ROOT / "core/tasks/engineering_goal_scheduler.py",
    REPO_ROOT / "core/tasks/runtime_repair_apply_transaction.py",
    REPO_ROOT / "core/tasks/engineering_memory_store.py",
]


class OkRuntime:
    def run(self, goals):
        records = [dict(goal) for goal in goals]
        goal_id = records[0]["goal_id"] if records else ""
        return {
            "ok": True,
            "schema": "fake.runtime",
            "state": "complete",
            "decision_state": "complete",
            "stop_reason": "complete",
            "iterations": [{"goal_id": goal_id, "state": "complete"}] if goal_id else [],
        }


def _issue(**fields: object) -> dict[str, object]:
    data: dict[str, object] = {
        "issue_id": "issue_blocking",
        "source_package_id": "package_1",
        "affected_files": ["core/tasks/other_layer.py"],
        "observed_symptom": "A non-mainline helper corrupts package results.",
        "root_cause_hypothesis": "The helper mutates shared result dictionaries in place.",
        "risk_level": "high",
        "blocks_current_task": True,
        "recommended_action": "fix_now",
        "reason_if_not_fixed_now": "",
        "created_at": 10,
    }
    data.update(fields)
    return data


def test_high_risk_blocking_issue_makes_goal_runner_success_disallowed(tmp_path) -> None:
    reporter = EngineeringIssueReporter(tmp_path, storage_path=tmp_path / "issues.json")
    reporter.report_issue(_issue())
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "goal_1", "summary": "Run goal"})

    result = EngineeringGoalRunner(
        repo_root=tmp_path,
        repository=repository,
        runtime_orchestrator=OkRuntime(),
        issue_reporter=reporter,
    ).run_goal("goal_1")

    assert result["runtime_result"]["ok"] is True
    assert result["ok"] is False
    assert result["success_allowed"] is False
    assert result["blocking_issues"][0]["issue_id"] == "issue_blocking"
    assert result["issues_found"][0]["issue_id"] == "issue_blocking"


def test_apply_issue_summary_does_not_block_nonblocking_issue(tmp_path) -> None:
    reporter = EngineeringIssueReporter(tmp_path, storage_path=tmp_path / "issues.json")
    reporter.report_issue(
        _issue(
            issue_id="issue_deferred",
            risk_level="medium",
            blocks_current_task=False,
            recommended_action="queue_for_next_package",
            reason_if_not_fixed_now="The current package reports the risk and defers the owning-layer fix to keep scope bounded.",
        )
    )

    result = apply_engineering_issue_summary({"ok": True, "result": "complete"}, repo_root=tmp_path, issue_reporter=reporter)

    assert result["ok"] is True
    assert result["success_allowed"] is True
    assert result["blocking_issues"] == []
    assert result["deferred_issues"][0]["issue_id"] == "issue_deferred"


def test_issue_contract_rejects_not_in_scope_only_reason(tmp_path) -> None:
    reporter = EngineeringIssueReporter(tmp_path)

    with pytest.raises(ValueError, match="cannot_only_be_not_in_scope"):
        reporter.report_issue(
            _issue(
                issue_id="issue_bad_reason",
                risk_level="medium",
                blocks_current_task=False,
                recommended_action="ignore_with_reason",
                reason_if_not_fixed_now="not in scope",
            )
        )


def test_boundary_scan_does_not_put_issue_reporting_into_runtime_scheduler_aer_memory_or_ui() -> None:
    forbidden_imports = {
        "EngineeringIssueReporter",
        "EngineeringIssueReport",
        "apply_engineering_issue_summary",
        "build_engineering_issue_summary",
        "core.tasks.engineering_issue_reporter",
        "core.tasks.engineering_issue_contract",
        "core.tasks.engineering_issue_summary",
        "ui",
    }

    for path in BOUNDARY_FILES:
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
                for alias in node.names:
                    imports.add(alias.name)
        assert imports.isdisjoint(forbidden_imports), path
