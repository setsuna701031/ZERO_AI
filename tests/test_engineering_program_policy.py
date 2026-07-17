from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_program_policy import EngineeringProgramPolicy


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_FILE = REPO_ROOT / "core/tasks/engineering_program_policy.py"


def _summary(portfolio_id: str, state: str) -> dict:
    return {"portfolio_id": portfolio_id, "state": state, "name": portfolio_id}


def test_policy_classifies_portfolio_state() -> None:
    policy = EngineeringProgramPolicy()

    assert policy.classify_portfolio_state(_summary("active", "active")) == "active"
    assert policy.classify_portfolio_state(_summary("done", "completed")) == "completed"
    assert policy.classify_portfolio_state(_summary("unknown", "weird")) == "active"


def test_only_active_portfolio_is_runnable() -> None:
    policy = EngineeringProgramPolicy()

    assert policy.is_runnable_portfolio(_summary("active", "active")) is True
    for state in ("completed", "blocked", "paused", "archived"):
        assert policy.is_runnable_portfolio(_summary(state, state)) is False
        assert policy.explain_skip_reason(_summary(state, state)) == f"portfolio_{state}"


def test_select_next_portfolio_is_deterministic_by_input_order() -> None:
    policy = EngineeringProgramPolicy()

    selection = policy.select_next_portfolio(
        [
            _summary("done", "completed"),
            _summary("blocked", "blocked"),
            _summary("first_active", "active"),
            _summary("second_active", "active"),
        ]
    )

    assert selection["ok"] is True
    assert selection["selected_portfolio_id"] == "first_active"
    assert [item["portfolio_id"] for item in selection["skipped_portfolios"]] == ["done", "blocked"]
    assert selection["selection_summary"]["runnable_portfolio_ids"] == ["first_active", "second_active"]
    assert selection["execution_path"]["deterministic_ref_order"] is True
    assert selection["execution_path"]["priority_algorithm"] is False


def test_select_next_portfolio_reports_no_runnable_portfolio() -> None:
    policy = EngineeringProgramPolicy()

    selection = policy.select_next_portfolio(
        [
            _summary("done", "completed"),
            _summary("paused", "paused"),
            _summary("archived", "archived"),
        ]
    )

    assert selection["ok"] is False
    assert selection["reason"] == "no_runnable_portfolio"
    assert selection["selected_portfolio_id"] == ""
    assert [item["reason"] for item in selection["skipped_portfolios"]] == [
        "portfolio_completed",
        "portfolio_paused",
        "portfolio_archived",
    ]


def test_build_selection_summary_counts_states() -> None:
    summary = EngineeringProgramPolicy().build_selection_summary(
        [
            _summary("active", "active"),
            _summary("done", "completed"),
            _summary("blocked", "blocked"),
            _summary("paused", "paused"),
        ]
    )

    assert summary["portfolio_count"] == 4
    assert summary["runnable_portfolio_ids"] == ["active"]
    assert summary["skipped_portfolio_count"] == 3
    assert summary["state_counts"] == {"active": 1, "completed": 1, "blocked": 1, "paused": 1}


def test_program_policy_does_not_import_goal_or_runtime_owners() -> None:
    tree = ast.parse(POLICY_FILE.read_text(encoding="utf-8"))
    imports: set[str] = set()
    calls: set[str] = set()

    def name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.Call):
            calls.add(name(node.func))

    forbidden = {
        "EngineeringGoalRepository",
        "EngineeringGoalRunner",
        "EngineeringGoalLoop",
        "EngineeringRuntimeOrchestrator",
        "EngineeringGoalScheduler",
        "EngineeringAdaptivePlanner",
        "core.tasks.engineering_goal_repository",
        "core.tasks.engineering_goal_runner",
        "core.tasks.engineering_goal_loop",
        "core.tasks.engineering_runtime_orchestrator",
        "core.tasks.engineering_goal_scheduler",
        "core.tasks.engineering_adaptive_planner",
        "core.runtime",
    }
    assert imports.isdisjoint(forbidden)
    assert "run_goal" not in calls
    assert "run_until_terminal" not in calls
    assert "schedule_next_goal" not in calls
