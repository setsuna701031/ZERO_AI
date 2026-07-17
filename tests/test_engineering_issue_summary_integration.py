from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from cli import program_cli
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_goal_runner import EngineeringGoalRunner
from core.tasks.engineering_issue_reporter import EngineeringIssueReporter
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_program_cycle import EngineeringProgramCycle
from core.tasks.engineering_program_repository import EngineeringProgramRepository
import pytest

pytestmark = [pytest.mark.integration]




REPO_ROOT = Path(__file__).resolve().parents[1]


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


class FakeCoordinator:
    def summarize_program_state(self, program_id: str) -> dict:
        return {
            "ok": True,
            "program_id": program_id,
            "state": "active",
            "completed_portfolio_count": 0,
            "blocked_portfolio_count": 0,
        }

    def select_next_portfolio(self, program_id: str) -> dict:
        return {
            "ok": False,
            "program_id": program_id,
            "reason": "no_runnable_portfolio",
            "selected_portfolio_id": "",
            "skipped_portfolios": [],
        }


class FakePortfolioCycle:
    def run_until_idle(self, portfolio_id: str) -> dict:
        return {"ok": True, "portfolio_id": portfolio_id}


def _issue(**fields: object) -> dict[str, object]:
    data: dict[str, object] = {
        "issue_id": "issue_nonblocking",
        "source_package_id": "package_1",
        "affected_files": ["core/tasks/other_layer.py"],
        "observed_symptom": "A non-mainline helper has unstable ordering.",
        "root_cause_hypothesis": "The helper relies on an unnormalized mapping.",
        "risk_level": "medium",
        "blocks_current_task": False,
        "recommended_action": "queue_for_next_package",
        "reason_if_not_fixed_now": "The current package only reports cross-package risk; queue the owning layer for a targeted fix.",
        "created_at": 10,
    }
    data.update(fields)
    return data


def _reporter(tmp_path: Path) -> EngineeringIssueReporter:
    return EngineeringIssueReporter(tmp_path, storage_path=tmp_path / "issues.json")


def test_goal_runner_summary_includes_nonblocking_issue_without_blocking_task(tmp_path) -> None:
    reporter = _reporter(tmp_path)
    reporter.report_issue(_issue())
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "goal_1", "summary": "Run goal"})

    result = EngineeringGoalRunner(
        repo_root=tmp_path,
        repository=repository,
        runtime_orchestrator=OkRuntime(),
        issue_reporter=reporter,
    ).run_goal("goal_1")

    assert result["ok"] is True
    assert result["success_allowed"] is True
    assert [issue["issue_id"] for issue in result["issues_found"]] == ["issue_nonblocking"]
    assert result["blocking_issues"] == []
    assert [issue["issue_id"] for issue in result["deferred_issues"]] == ["issue_nonblocking"]


def test_program_cycle_summary_includes_issue_fields(tmp_path) -> None:
    reporter = _reporter(tmp_path)
    reporter.report_issue(_issue())

    result = EngineeringProgramCycle(
        repo_root=tmp_path,
        coordinator=FakeCoordinator(),
        portfolio_cycle=FakePortfolioCycle(),
        issue_reporter=reporter,
    ).run_until_idle("program_1")

    assert result["ok"] is True
    assert "issues_found" in result
    assert "blocking_issues" in result
    assert "deferred_issues" in result
    assert result["success_allowed"] is True
    assert result["deferred_issues"][0]["issue_id"] == "issue_nonblocking"


def test_program_summary_cli_displays_issues_section(tmp_path, monkeypatch, capsys) -> None:
    program_store = tmp_path / "programs.json"
    portfolio_store = tmp_path / "portfolios.json"
    issue_store = tmp_path / "issues.json"
    program_repository = EngineeringProgramRepository(tmp_path, storage_path=program_store)
    portfolio_repository = EngineeringPortfolioRepository(tmp_path, storage_path=portfolio_store)
    program_repository.create_program({"program_id": "program_1", "name": "Issue summary"})
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Portfolio"})
    program_repository.add_portfolio("program_1", "portfolio_1")
    EngineeringIssueReporter(tmp_path, storage_path=issue_store).report_issue(_issue())
    monkeypatch.setenv("ZERO_PROGRAM_STORE", str(program_store))
    monkeypatch.setenv("ZERO_PORTFOLIO_STORE", str(portfolio_store))
    monkeypatch.setenv("ZERO_ISSUE_STORE", str(issue_store))

    handled = program_cli.try_handle_program_command(["program", "summary", "program_1"], repo_root=REPO_ROOT)
    payload = json.loads(capsys.readouterr().out)

    assert handled is True
    summary = payload["program_summary"]
    assert payload["ok"] is True
    assert summary["issues_found"][0]["issue_id"] == "issue_nonblocking"
    assert summary["blocking_issues"] == []
    assert summary["deferred_issues"][0]["issue_id"] == "issue_nonblocking"
    assert summary["success_allowed"] is True


def test_app_program_summary_process_displays_issues_section(tmp_path) -> None:
    program_store = tmp_path / "programs.json"
    portfolio_store = tmp_path / "portfolios.json"
    issue_store = tmp_path / "issues.json"
    program_repository = EngineeringProgramRepository(tmp_path, storage_path=program_store)
    portfolio_repository = EngineeringPortfolioRepository(tmp_path, storage_path=portfolio_store)
    program_repository.create_program({"program_id": "program_1", "name": "Issue summary"})
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Portfolio"})
    program_repository.add_portfolio("program_1", "portfolio_1")
    EngineeringIssueReporter(tmp_path, storage_path=issue_store).report_issue(_issue())

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "app.py"), "program", "summary", "program_1"],
        cwd=REPO_ROOT,
        env={
            **dict(os.environ),
            "ZERO_PROGRAM_STORE": str(program_store),
            "ZERO_PORTFOLIO_STORE": str(portfolio_store),
            "ZERO_ISSUE_STORE": str(issue_store),
            "PYTHONPATH": str(REPO_ROOT),
        },
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["program_summary"]["issues_found"][0]["issue_id"] == "issue_nonblocking"
