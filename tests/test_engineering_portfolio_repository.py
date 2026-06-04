from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_portfolio_repository import (
    ENGINEERING_PORTFOLIO_REPOSITORY_SCHEMA,
    ENGINEERING_PORTFOLIO_SCHEMA,
    EngineeringPortfolio,
    EngineeringPortfolioRepository,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO_FILE = REPO_ROOT / "core/tasks/engineering_portfolio_repository.py"


def test_create_load_update_and_list_portfolio(tmp_path) -> None:
    repository = EngineeringPortfolioRepository(tmp_path)

    created = repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Runtime work"})
    updated = repository.update_portfolio("portfolio_1", {"description": "Long horizon engineering"})
    loaded = repository.load_portfolio("portfolio_1")
    listed = repository.list_portfolios()

    assert created["schema"] == ENGINEERING_PORTFOLIO_SCHEMA
    assert created["portfolio_id"] == "portfolio_1"
    assert created["name"] == "Runtime work"
    assert created["goal_ids"] == []
    assert updated["description"] == "Long horizon engineering"
    assert loaded == updated
    assert listed == [updated]
    assert repository.storage_path == tmp_path / "runtime" / "portfolios" / "portfolios.json"


def test_portfolio_goal_refs_are_added_removed_and_persisted(tmp_path) -> None:
    repository = EngineeringPortfolioRepository(tmp_path)
    repository.create_portfolio("Platform goals")

    portfolio_id = repository.list_portfolios()[0]["portfolio_id"]
    added = repository.add_goal_to_portfolio(portfolio_id, "goal_1")
    duplicate = repository.add_goal_to_portfolio(portfolio_id, "goal_1")
    repository.add_goal_to_portfolio(portfolio_id, "goal_2")
    refs_after_restart = EngineeringPortfolioRepository(tmp_path).list_portfolio_goals(portfolio_id)
    removed = EngineeringPortfolioRepository(tmp_path).remove_goal_from_portfolio(portfolio_id, "goal_1")

    assert added["goal_ids"] == ["goal_1"]
    assert duplicate["goal_ids"] == ["goal_1"]
    assert refs_after_restart == ["goal_1", "goal_2"]
    assert removed["goal_ids"] == ["goal_2"]


def test_portfolio_dataclass_normalizes_goal_refs() -> None:
    portfolio = EngineeringPortfolio.from_mapping(
        {
            "portfolio_id": "portfolio_1",
            "name": "Normalize refs",
            "goal_ids": ["goal_1", "goal_1", "", "goal_2"],
        }
    )

    assert portfolio.as_dict()["goal_ids"] == ["goal_1", "goal_2"]


def test_portfolio_repository_file_schema(tmp_path) -> None:
    repository = EngineeringPortfolioRepository(tmp_path)
    repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Schema proof"})

    text = repository.storage_path.read_text(encoding="utf-8")

    assert ENGINEERING_PORTFOLIO_REPOSITORY_SCHEMA in text
    assert "portfolio_1" in text


def test_portfolio_repository_does_not_import_execution_owners() -> None:
    tree = ast.parse(PORTFOLIO_FILE.read_text(encoding="utf-8"))
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
        "EngineeringGoalRunner",
        "EngineeringGoalLoop",
        "EngineeringRuntimeOrchestrator",
        "EngineeringGoalScheduler",
        "EngineeringAdaptivePlanner",
        "run_engineering_task",
        "core.tasks.engineering_goal_runner",
        "core.tasks.engineering_goal_loop",
        "core.tasks.engineering_runtime_orchestrator",
        "core.tasks.engineering_goal_scheduler",
    }
    assert imports.isdisjoint(forbidden)
    assert "run_goal" not in calls
    assert "run_until_terminal" not in calls
    assert "schedule_next_goal" not in calls
