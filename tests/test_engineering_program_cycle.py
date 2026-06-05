from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_program_cycle import EngineeringProgramCycle


REPO_ROOT = Path(__file__).resolve().parents[1]
PROGRAM_CYCLE_FILE = REPO_ROOT / "core/tasks/engineering_program_cycle.py"


class FakeProgramCoordinator:
    def __init__(self, states: list[dict], selections: list[dict]) -> None:
        self.states = list(states)
        self.selections = list(selections)
        self.state_calls: list[str] = []
        self.selection_calls: list[str] = []

    def summarize_program_state(self, program_id: str) -> dict:
        self.state_calls.append(program_id)
        if len(self.states) > 1:
            return self.states.pop(0)
        return self.states[0]

    def select_next_portfolio(self, program_id: str) -> dict:
        self.selection_calls.append(program_id)
        if self.selections:
            return self.selections.pop(0)
        return {
            "ok": False,
            "program_id": program_id,
            "reason": "no_runnable_portfolio",
            "selected_portfolio_id": "",
            "skipped_portfolios": [],
        }


class FakePortfolioCycle:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run_until_idle(self, portfolio_id: str) -> dict:
        self.calls.append(portfolio_id)
        return {
            "ok": True,
            "portfolio_id": portfolio_id,
            "stop_reason": "portfolio_completed",
            "cycle_count": 1,
        }


def _program_state(state: str, completed: int = 0, blocked: int = 0) -> dict:
    return {
        "ok": True,
        "program_id": "program_1",
        "state": state,
        "completed_portfolio_count": completed,
        "blocked_portfolio_count": blocked,
        "active_portfolio_count": 1 if state == "active" else 0,
        "progress": {
            "completed_portfolio_count": completed,
            "blocked_portfolio_count": blocked,
        },
    }


def _selection(portfolio_id: str, skipped: list[dict] | None = None) -> dict:
    return {
        "ok": True,
        "program_id": "program_1",
        "reason": "selected",
        "selected_portfolio_id": portfolio_id,
        "skipped_portfolios": skipped or [],
    }


def _cycle(coordinator: FakeProgramCoordinator, portfolio_cycle: FakePortfolioCycle) -> EngineeringProgramCycle:
    return EngineeringProgramCycle(
        repo_root=REPO_ROOT,
        coordinator=coordinator,
        portfolio_cycle=portfolio_cycle,
    )


def test_program_cycle_delegates_selected_portfolio_to_portfolio_cycle() -> None:
    coordinator = FakeProgramCoordinator(
        states=[_program_state("active"), _program_state("completed", completed=1)],
        selections=[_selection("portfolio_1")],
    )
    portfolio_cycle = FakePortfolioCycle()

    result = _cycle(coordinator, portfolio_cycle).run_cycle("program_1")

    assert result["stop_reason"] == "program_completed"
    assert result["cycle_count"] == 1
    assert result["executed_portfolio_count"] == 1
    assert result["completed_portfolio_count"] == 1
    assert portfolio_cycle.calls == ["portfolio_1"]
    assert coordinator.selection_calls == ["program_1"]


def test_run_until_idle_stops_when_no_runnable_portfolio() -> None:
    coordinator = FakeProgramCoordinator(
        states=[_program_state("active"), _program_state("active")],
        selections=[
            {
                "ok": False,
                "program_id": "program_1",
                "reason": "no_runnable_portfolio",
                "selected_portfolio_id": "",
                "skipped_portfolios": [{"portfolio_id": "done", "reason": "portfolio_completed"}],
            }
        ],
    )
    portfolio_cycle = FakePortfolioCycle()

    result = _cycle(coordinator, portfolio_cycle).run_until_idle("program_1")

    assert result["ok"] is True
    assert result["stop_reason"] == "no_runnable_portfolio"
    assert result["cycle_count"] == 0
    assert result["executed_portfolio_count"] == 0
    assert result["skipped_portfolio_count"] == 1
    assert portfolio_cycle.calls == []


def test_run_until_idle_stops_when_program_blocks() -> None:
    coordinator = FakeProgramCoordinator(
        states=[_program_state("active"), _program_state("blocked", blocked=1)],
        selections=[_selection("portfolio_1")],
    )
    portfolio_cycle = FakePortfolioCycle()

    result = _cycle(coordinator, portfolio_cycle).run_until_idle("program_1")

    assert result["stop_reason"] == "program_blocked"
    assert result["cycle_count"] == 1
    assert result["blocked_portfolio_count"] == 1
    assert portfolio_cycle.calls == ["portfolio_1"]


def test_run_until_idle_stops_at_max_portfolios() -> None:
    coordinator = FakeProgramCoordinator(
        states=[_program_state("active"), _program_state("active"), _program_state("active")],
        selections=[_selection("portfolio_1"), _selection("portfolio_2")],
    )
    portfolio_cycle = FakePortfolioCycle()

    result = _cycle(coordinator, portfolio_cycle).run_until_idle("program_1", max_portfolios=2)

    assert result["stop_reason"] == "max_portfolios_reached"
    assert result["cycle_count"] == 2
    assert result["executed_portfolio_count"] == 2
    assert portfolio_cycle.calls == ["portfolio_1", "portfolio_2"]


def test_build_cycle_summary_counts_unique_skipped_portfolios() -> None:
    coordinator = FakeProgramCoordinator(states=[_program_state("active")], selections=[])
    portfolio_cycle = FakePortfolioCycle()

    summary = _cycle(coordinator, portfolio_cycle).build_cycle_summary(
        program_id="program_1",
        runs=[{"selected_portfolio_id": "portfolio_1"}],
        selections=[
            {"skipped_portfolios": [{"portfolio_id": "done"}, {"portfolio_id": "blocked"}]},
            {"skipped_portfolios": [{"portfolio_id": "done"}]},
        ],
        stop_reason="no_runnable_portfolio",
        program_state=_program_state("active", completed=1, blocked=1),
        max_portfolios=5,
    )

    assert summary["cycle_count"] == 1
    assert summary["executed_portfolio_count"] == 1
    assert summary["completed_portfolio_count"] == 1
    assert summary["blocked_portfolio_count"] == 1
    assert summary["skipped_portfolio_count"] == 2


def test_program_cycle_boundary_imports_only_allowed_owners() -> None:
    tree = ast.parse(PROGRAM_CYCLE_FILE.read_text(encoding="utf-8"))
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
        "EngineeringGoalLoop",
        "GoalLoop",
        "RuntimeOrchestrator",
        "EngineeringRuntimeOrchestrator",
        "Scheduler",
        "EngineeringGoalScheduler",
        "AdaptivePlanner",
        "EngineeringAdaptivePlanner",
        "Memory",
        "AER",
        "core.tasks.engineering_goal_loop",
        "core.tasks.engineering_runtime_orchestrator",
        "core.tasks.scheduler",
        "core.tasks.engineering_goal_scheduler",
        "core.tasks.engineering_adaptive_planner",
        "core.memory",
    }
    required = {
        "EngineeringProgramCoordinator",
        "EngineeringPortfolioCycle",
        "EngineeringProgramState",
    }
    assert imports.isdisjoint(forbidden)
    assert required.issubset(imports)
