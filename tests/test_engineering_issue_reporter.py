from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cli import issue_cli
from core.tasks.engineering_issue_reporter import EngineeringIssueReporter
pytestmark = [pytest.mark.integration]




REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTER_FILE = REPO_ROOT / "core/tasks/engineering_issue_reporter.py"
CLI_FILE = REPO_ROOT / "cli/issue_cli.py"


def _issue(**fields: object) -> dict[str, object]:
    data: dict[str, object] = {
        "issue_id": "issue_ordering",
        "source_package_id": "package_1",
        "affected_files": ["core/tasks/other_layer.py"],
        "observed_symptom": "Non-mainline helper returns unstable ordering.",
        "root_cause_hypothesis": "The helper sorts by display name instead of stable id.",
        "risk_level": "medium",
        "blocks_current_task": False,
        "recommended_action": "queue_for_next_package",
        "reason_if_not_fixed_now": "The current package is limited to reporting; queue a targeted package for the owning layer.",
        "created_at": 10,
    }
    data.update(fields)
    return data


def test_reporter_saves_and_reads_json_record(tmp_path) -> None:
    store = tmp_path / "issues.json"
    reporter = EngineeringIssueReporter(tmp_path, storage_path=store)

    created = reporter.report_issue(_issue())
    listed = reporter.list_issues()
    shown = reporter.get_issue("issue_ordering")
    raw = json.loads(store.read_text(encoding="utf-8"))

    assert created["issue_id"] == "issue_ordering"
    assert listed == [created]
    assert shown == created
    assert raw["schema"] == "zero.engineering_issue_reporter.v1"
    assert raw["issues"][0]["issue_id"] == "issue_ordering"


def test_reporter_rejects_ignore_without_reason(tmp_path) -> None:
    reporter = EngineeringIssueReporter(tmp_path)

    with pytest.raises(ValueError, match="requires_reason"):
        reporter.report_issue(_issue(recommended_action="ignore_with_reason", reason_if_not_fixed_now=""))


def test_reporter_success_gate_rejects_high_risk_blocking_issue(tmp_path) -> None:
    reporter = EngineeringIssueReporter(tmp_path)
    reporter.report_issue(
        _issue(
            issue_id="issue_blocking",
            risk_level="high",
            blocks_current_task=True,
            recommended_action="fix_now",
            reason_if_not_fixed_now="",
        )
    )

    gate = reporter.success_gate()
    summary = reporter.build_summary()

    assert gate["ok"] is False
    assert gate["success_allowed"] is False
    assert gate["blocking_issues"][0]["issue_id"] == "issue_blocking"
    assert summary["success_allowed"] is False
    assert summary["blocking_issue_count"] == 1


def test_issue_cli_can_list_and_show_issues(tmp_path, monkeypatch, capsys) -> None:
    store = tmp_path / "issues.json"
    reporter = EngineeringIssueReporter(tmp_path, storage_path=store)
    reporter.report_issue(_issue())
    monkeypatch.setenv("ZERO_ISSUE_STORE", str(store))

    handled_list = issue_cli.try_handle_issue_command(["issue", "list"], repo_root=REPO_ROOT)
    list_payload = json.loads(capsys.readouterr().out)
    handled_show = issue_cli.try_handle_issue_command(["issue", "show", "issue_ordering"], repo_root=REPO_ROOT)
    show_payload = json.loads(capsys.readouterr().out)

    assert handled_list is True
    assert handled_show is True
    assert list_payload["ok"] is True
    assert [item["issue_id"] for item in list_payload["issues"]] == ["issue_ordering"]
    assert show_payload["issue"]["observed_symptom"] == "Non-mainline helper returns unstable ordering."


def test_app_issue_list_process_smoke(tmp_path) -> None:
    store = tmp_path / "issues.json"
    EngineeringIssueReporter(tmp_path, storage_path=store).report_issue(_issue())
    env = {
        **dict(os.environ),
        "ZERO_ISSUE_STORE": str(store),
        "PYTHONPATH": str(REPO_ROOT),
    }

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "app.py"), "issue", "list"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["issues"][0]["issue_id"] == "issue_ordering"


def test_issue_reporter_and_cli_boundary_imports_no_runtime_scheduler_aer_memory_or_ui() -> None:
    forbidden = {
        "RuntimeOrchestrator",
        "EngineeringRuntimeOrchestrator",
        "Scheduler",
        "GoalLoop",
        "EngineeringGoalLoop",
        "GoalRunner",
        "EngineeringGoalRunner",
        "AER",
        "Memory",
        "UI",
        "core.runtime",
        "core.tasks.scheduler",
        "core.tasks.engineering_runtime_orchestrator",
        "core.tasks.engineering_goal_loop",
        "core.tasks.engineering_goal_runner",
        "core.memory",
        "ui",
    }

    for path in (REPORTER_FILE, CLI_FILE):
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
        assert imports.isdisjoint(forbidden)
