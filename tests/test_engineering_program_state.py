from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_program_repository import EngineeringProgramRepository
from core.tasks.engineering_program_state import EngineeringProgramState


REPO_ROOT = Path(__file__).resolve().parents[1]
PROGRAM_STATE_FILE = REPO_ROOT / "core/tasks/engineering_program_state.py"


def _state(tmp_path: Path, states: dict[str, str]) -> EngineeringProgramState:
    program_repository = EngineeringProgramRepository(tmp_path)
    portfolio_repository = EngineeringPortfolioRepository(tmp_path)
    program_repository.create_program({"program_id": "program_1", "name": "State program"})
    for portfolio_id, state in states.items():
        fields = {"portfolio_id": portfolio_id, "name": portfolio_id}
        if state != "active":
            fields["lifecycle_state"] = state
        portfolio_repository.create_portfolio(fields)
        program_repository.add_portfolio("program_1", portfolio_id)
    return EngineeringProgramState(
        tmp_path,
        program_repository=program_repository,
        portfolio_repository=portfolio_repository,
    )


def test_all_completed_portfolios_complete_program(tmp_path) -> None:
    state = _state(tmp_path, {"portfolio_1": "completed", "portfolio_2": "completed"})

    result = state.evaluate_program_state("program_1")

    assert result["ok"] is True
    assert result["state"] == "completed"
    assert result["portfolio_count"] == 2
    assert result["completed_portfolio_count"] == 2
    assert result["completion_ratio"] == 1.0


def test_blocked_without_active_blocks_program(tmp_path) -> None:
    state = _state(tmp_path, {"blocked": "blocked", "paused": "paused", "done": "completed"})

    result = state.evaluate_program_state("program_1")

    assert result["state"] == "blocked"
    assert result["blocked_portfolio_count"] == 1
    assert result["active_portfolio_count"] == 0


def test_any_active_portfolio_makes_program_active(tmp_path) -> None:
    state = _state(tmp_path, {"blocked": "blocked", "active": "active"})

    result = state.evaluate_program_state("program_1")

    assert result["state"] == "active"
    assert result["active_portfolio_count"] == 1


def test_all_archived_portfolios_archive_program(tmp_path) -> None:
    state = _state(tmp_path, {"archived_1": "archived", "archived_2": "archived"})

    result = state.evaluate_program_state("program_1")

    assert result["state"] == "archived"
    assert result["portfolio_count"] == 2
    assert result["active_portfolio_count"] == 0


def test_all_paused_portfolios_pause_program(tmp_path) -> None:
    state = _state(tmp_path, {"paused_1": "paused", "paused_2": "paused"})

    result = state.evaluate_program_state("program_1")

    assert result["state"] == "paused"


def test_program_progress_counts_portfolio_states(tmp_path) -> None:
    state = _state(tmp_path, {"done": "completed", "blocked": "blocked", "active": "active", "paused": "paused"})

    progress = state.calculate_program_progress("program_1")

    assert progress["portfolio_count"] == 4
    assert progress["completed_portfolio_count"] == 1
    assert progress["blocked_portfolio_count"] == 1
    assert progress["active_portfolio_count"] == 1
    assert progress["completion_ratio"] == 0.25


def test_program_state_does_not_import_goal_or_runtime_owners() -> None:
    tree = ast.parse(PROGRAM_STATE_FILE.read_text(encoding="utf-8"))
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
