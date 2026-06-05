from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_program_coordinator import EngineeringProgramCoordinator
from core.tasks.engineering_program_repository import EngineeringProgramRepository


REPO_ROOT = Path(__file__).resolve().parents[1]
PROGRAM_COORDINATOR_FILE = REPO_ROOT / "core/tasks/engineering_program_coordinator.py"


class FakePortfolioStateCoordinator:
    def __init__(self, states: dict[str, str]) -> None:
        self.states = states

    def summarize_portfolio_state(self, portfolio_id: str) -> dict:
        state = self.states.get(portfolio_id, "active")
        return {
            "ok": True,
            "portfolio_id": portfolio_id,
            "state": state,
            "progress": {},
        }


class FakePortfolioCycle:
    def __init__(self, states: dict[str, str] | None = None) -> None:
        self.coordinator = FakePortfolioStateCoordinator(states or {})
        self.calls: list[tuple[str, int]] = []

    def run_until_idle(self, portfolio_id: str, max_goals: int = 1) -> dict:
        self.calls.append((portfolio_id, max_goals))
        return {
            "ok": True,
            "portfolio_id": portfolio_id,
            "stop_reason": "portfolio_cycle_finished",
            "cycle_count": 1,
            "runs": [{"portfolio_id": portfolio_id}],
        }


def _coordinator(tmp_path: Path, states: dict[str, str]):
    program_repository = EngineeringProgramRepository(tmp_path)
    portfolio_repository = EngineeringPortfolioRepository(tmp_path)
    portfolio_cycle = FakePortfolioCycle(states)
    program_repository.create_program({"program_id": "program_1", "name": "Program"})
    for portfolio_id, state in states.items():
        fields = {"portfolio_id": portfolio_id, "name": portfolio_id}
        if state != "active":
            fields["lifecycle_state"] = state
        portfolio_repository.create_portfolio(fields)
        program_repository.add_portfolio("program_1", portfolio_id)
    return (
        EngineeringProgramCoordinator(
            repo_root=tmp_path,
            program_repository=program_repository,
            portfolio_repository=portfolio_repository,
            portfolio_cycle=portfolio_cycle,
        ),
        portfolio_cycle,
    )


def test_select_next_portfolio_uses_program_ref_order_and_skips_terminal_states(tmp_path) -> None:
    coordinator, _cycle = _coordinator(
        tmp_path,
        {
            "archived": "archived",
            "completed": "completed",
            "blocked": "blocked",
            "paused": "paused",
            "active": "active",
        },
    )

    selection = coordinator.select_next_portfolio("program_1")

    assert selection["ok"] is True
    assert selection["selected_portfolio_id"] == "active"
    assert [item["portfolio_id"] for item in selection["skipped_portfolios"]] == ["archived", "completed", "blocked", "paused"]
    assert selection["execution_path"]["deterministic_ref_order"] is True
    assert selection["execution_path"]["priority_algorithm"] is False
    assert selection["execution_path"]["scheduler_used"] is False


def test_no_runnable_portfolio_is_not_reported_as_success(tmp_path) -> None:
    coordinator, _cycle = _coordinator(tmp_path, {"done": "completed", "blocked": "blocked"})

    selection = coordinator.select_next_portfolio("program_1")
    run = coordinator.run_next_portfolio("program_1")
    cycle = coordinator.run_program_cycle("program_1")

    assert selection["ok"] is False
    assert selection["reason"] == "no_runnable_portfolio"
    assert run["ok"] is False
    assert run["reason"] == "no_runnable_portfolio"
    assert cycle["ok"] is False
    assert cycle["stop_reason"] == "no_runnable_portfolio"


def test_run_next_portfolio_delegates_to_portfolio_cycle(tmp_path) -> None:
    coordinator, portfolio_cycle = _coordinator(tmp_path, {"active_1": "active", "active_2": "active"})

    result = coordinator.run_next_portfolio("program_1")

    assert result["ok"] is True
    assert result["selected_portfolio_id"] == "active_1"
    assert result["cycle_result"]["portfolio_id"] == "active_1"
    assert portfolio_cycle.calls == [("active_1", 1)]


def test_run_program_cycle_delegates_one_portfolio_by_default(tmp_path) -> None:
    coordinator, portfolio_cycle = _coordinator(tmp_path, {"active_1": "active", "active_2": "active"})

    result = coordinator.run_program_cycle("program_1")

    assert result["ok"] is True
    assert result["run_count"] == 1
    assert result["runs"][0]["selected_portfolio_id"] == "active_1"
    assert portfolio_cycle.calls == [("active_1", 1)]


def test_summarize_program_state_lists_runnable_and_skipped_portfolios(tmp_path) -> None:
    coordinator, _cycle = _coordinator(tmp_path, {"active": "active", "paused": "paused", "archived": "archived"})

    summary = coordinator.summarize_program_state("program_1")

    assert summary["ok"] is True
    assert summary["portfolio_count"] == 3
    assert summary["runnable_portfolio_ids"] == ["active"]
    assert [item["portfolio_id"] for item in summary["skipped_portfolios"]] == ["paused", "archived"]


def test_program_coordinator_does_not_import_goal_or_runtime_owners() -> None:
    tree = ast.parse(PROGRAM_COORDINATOR_FILE.read_text(encoding="utf-8"))
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
