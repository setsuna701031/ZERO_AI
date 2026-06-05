from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from core.tasks.engineering_issue_contract import EngineeringIssueReport, validate_issue_reports_allow_success


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FILE = REPO_ROOT / "core/tasks/engineering_issue_contract.py"


def _report(**fields: object) -> EngineeringIssueReport:
    data = {
        "issue_id": "issue_1",
        "source_package_id": "package_1",
        "affected_files": ["core/tasks/example.py"],
        "observed_symptom": "A helper outside the current package returns unstable ordering.",
        "root_cause_hypothesis": "The helper relies on insertion order from an unnormalized mapping.",
        "risk_level": "medium",
        "blocks_current_task": False,
        "recommended_action": "queue_for_next_package",
        "reason_if_not_fixed_now": "Current package does not own the helper; queue a focused follow-up to avoid widening this change.",
        "created_at": 10,
    }
    data.update(fields)
    return EngineeringIssueReport.from_mapping(data)


def test_issue_report_serializes_to_json_and_round_trips() -> None:
    report = _report()

    payload = report.to_dict()
    encoded = report.to_json()
    decoded = json.loads(encoded)
    round_trip = EngineeringIssueReport.from_mapping(decoded)

    assert payload["schema"] == "zero.engineering_issue_report.v1"
    assert decoded["issue_id"] == "issue_1"
    assert round_trip.to_dict() == payload


def test_ignore_with_reason_requires_reason_if_not_fixed_now() -> None:
    with pytest.raises(ValueError, match="requires_reason"):
        _report(recommended_action="ignore_with_reason", reason_if_not_fixed_now="")


def test_non_fix_action_cannot_only_say_not_in_scope() -> None:
    with pytest.raises(ValueError, match="cannot_only_be_not_in_scope"):
        _report(recommended_action="queue_for_next_package", reason_if_not_fixed_now="not in scope")


def test_high_risk_blocking_issue_disallows_success() -> None:
    report = _report(risk_level="high", blocks_current_task=True, recommended_action="fix_now", reason_if_not_fixed_now="")

    result = validate_issue_reports_allow_success([report])

    assert report.blocks_success is True
    assert result["ok"] is False
    assert result["success_allowed"] is False
    assert result["blocking_issues"][0]["issue_id"] == "issue_1"


def test_low_or_nonblocking_issue_allows_success_gate() -> None:
    high_nonblocking = _report(risk_level="high", blocks_current_task=False)
    medium_blocking = _report(risk_level="medium", blocks_current_task=True)

    result = validate_issue_reports_allow_success([high_nonblocking, medium_blocking])

    assert result["ok"] is True
    assert result["success_allowed"] is True
    assert result["blocking_issue_count"] == 0


def test_issue_contract_boundary_imports_no_runtime_scheduler_aer_memory_or_ui() -> None:
    tree = ast.parse(CONTRACT_FILE.read_text(encoding="utf-8"))
    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
            for alias in node.names:
                imports.add(alias.name)

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
    assert imports.isdisjoint(forbidden)
