from __future__ import annotations

import ast
import json
from pathlib import Path

from cli import portfolio_cli


REPO_ROOT = Path(__file__).resolve().parents[1]
CYCLE_FILE = REPO_ROOT / "core/tasks/engineering_portfolio_cycle.py"


class FakePortfolioCycle:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int | None]] = []

    def run_cycle(self, portfolio_id: str) -> dict:
        self.calls.append(("cycle", portfolio_id, None))
        return _cycle_payload(portfolio_id, max_goals=5)

    def run_until_idle(self, portfolio_id: str, max_goals: int = 5) -> dict:
        self.calls.append(("run_until_idle", portfolio_id, max_goals))
        return _cycle_payload(portfolio_id, max_goals=max_goals)


def _cycle_payload(portfolio_id: str, *, max_goals: int) -> dict:
    return {
        "schema": "zero.engineering_portfolio_cycle.summary.v1",
        "ok": True,
        "portfolio_id": portfolio_id,
        "stop_reason": "no_runnable_goal",
        "max_goals": max_goals,
        "cycle_count": 2,
        "executed_goal_count": 2,
        "completed_goal_count": 2,
        "blocked_goal_count": 1,
        "skipped_goal_count": 1,
        "runs": [{"selected_goal_id": "goal_1"}, {"selected_goal_id": "goal_2"}],
        "portfolio_state": {"state": "active", "progress": {"completed_goal_count": 2, "blocked_goal_count": 1}},
    }


def test_portfolio_cycle_cli_smoke(monkeypatch, capsys) -> None:
    fake_cycle = FakePortfolioCycle()
    monkeypatch.setattr(portfolio_cli, "_portfolio_cycle", lambda repo_root: fake_cycle)

    handled = portfolio_cli.try_handle_portfolio_command(["portfolio", "cycle", "portfolio_1"], repo_root=REPO_ROOT)
    payload = json.loads(capsys.readouterr().out)

    assert handled is True
    assert payload["ok"] is True
    assert payload["cycle_summary"]["cycle_count"] == 2
    assert payload["cycle_summary"]["executed_goal_count"] == 2
    assert "completed_goal_count" in payload["cycle_summary"]
    assert "blocked_goal_count" in payload["cycle_summary"]
    assert "skipped_goal_count" in payload["cycle_summary"]
    assert "portfolio_state" in payload["cycle_summary"]
    assert fake_cycle.calls == [("cycle", "portfolio_1", None)]


def test_portfolio_run_until_idle_cli_smoke(monkeypatch, capsys) -> None:
    fake_cycle = FakePortfolioCycle()
    monkeypatch.setattr(portfolio_cli, "_portfolio_cycle", lambda repo_root: fake_cycle)

    handled = portfolio_cli.try_handle_portfolio_command(["portfolio", "run-until-idle", "portfolio_1"], repo_root=REPO_ROOT)
    payload = json.loads(capsys.readouterr().out)

    assert handled is True
    assert payload["ok"] is True
    assert payload["cycle_summary"]["cycle_count"] == 2
    assert payload["cycle_summary"]["executed_goal_count"] == 2
    assert payload["cycle_summary"]["max_goals"] == 5
    assert fake_cycle.calls == [("run_until_idle", "portfolio_1", 5)]


def test_portfolio_cycle_boundary_imports_only_allowed_owners() -> None:
    tree = ast.parse(CYCLE_FILE.read_text(encoding="utf-8"))
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
        "EngineeringRuntimeOrchestrator",
        "EngineeringGoalScheduler",
        "EngineeringAdaptivePlanner",
        "core.tasks.scheduler",
        "core.tasks.engineering_runtime_orchestrator",
        "core.tasks.engineering_goal_scheduler",
        "core.tasks.engineering_adaptive_planner",
        "core.tasks.engineering_memory_store",
    }
    required = {
        "EngineeringPortfolioCoordinator",
        "EngineeringGoalLoop",
        "EngineeringPortfolioRepository",
        "EngineeringGoalRepository",
    }
    assert imports.isdisjoint(forbidden)
    assert required.issubset(imports)
