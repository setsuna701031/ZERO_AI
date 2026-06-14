from __future__ import annotations

import ast
from pathlib import Path

from core.evidence import EvidenceRecord, EvidenceValidator
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_program_observability import EngineeringProgramObservability
from core.tasks.engineering_program_repository import EngineeringProgramRepository


REPO_ROOT = Path(__file__).resolve().parents[1]
OBSERVABILITY_FILE = REPO_ROOT / "core/tasks/engineering_program_observability.py"


def _attestation(goal_id: str):
    evidence = EvidenceValidator().validate(EvidenceRecord("seed-e", goal_id, None, "test", "ok", "now"))
    return GoalCompletionAuthority().complete_goal(goal_id=goal_id, evidence_refs=[evidence], all_subgoals_completed=True)


def _fixture(tmp_path: Path) -> EngineeringProgramObservability:
    program_repository = EngineeringProgramRepository(tmp_path)
    portfolio_repository = EngineeringPortfolioRepository(tmp_path)
    goal_repository = EngineeringGoalRepository(tmp_path)

    program_repository.create_program({"program_id": "program_1", "name": "Observable program"})
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_done", "name": "Done portfolio"})
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_blocked", "name": "Blocked portfolio"})
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_active", "name": "Active portfolio"})
    for portfolio_id in ("portfolio_done", "portfolio_blocked", "portfolio_active"):
        program_repository.add_portfolio("program_1", portfolio_id)

    goal_repository.save_goal(
        {"goal_id": "goal_done", "summary": "Finished goal", "status": "complete"},
        completion_attestation=_attestation("goal_done"),
    )
    goal_repository.save_goal({"goal_id": "goal_blocked_1", "summary": "Blocked goal 1", "status": "blocked"})
    goal_repository.save_goal({"goal_id": "goal_blocked_2", "summary": "Blocked goal 2", "status": "blocked"})
    goal_repository.save_goal({"goal_id": "goal_active", "summary": "Active goal", "status": "pending"})

    portfolio_repository.add_goal_to_portfolio("portfolio_done", "goal_done")
    portfolio_repository.add_goal_to_portfolio("portfolio_blocked", "goal_blocked_1")
    portfolio_repository.add_goal_to_portfolio("portfolio_blocked", "goal_blocked_2")
    portfolio_repository.add_goal_to_portfolio("portfolio_active", "goal_active")

    return EngineeringProgramObservability(
        tmp_path,
        program_repository=program_repository,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
    )


def test_calculate_rollup_metrics_counts_portfolios_goals_and_ratio(tmp_path) -> None:
    observability = _fixture(tmp_path)

    metrics = observability.calculate_rollup_metrics("program_1")

    assert metrics["ok"] is True
    assert metrics["program_id"] == "program_1"
    assert metrics["program_state"] == "active"
    assert metrics["portfolio_count"] == 3
    assert metrics["completed_portfolio_count"] == 1
    assert metrics["blocked_portfolio_count"] == 1
    assert metrics["active_portfolio_count"] == 1
    assert metrics["goal_count"] == 4
    assert metrics["completed_goal_count"] == 1
    assert metrics["blocked_goal_count"] == 2
    assert metrics["active_goal_count"] == 1
    assert metrics["completion_ratio"] == 0.25


def test_blocked_and_active_items_are_listed(tmp_path) -> None:
    observability = _fixture(tmp_path)

    blocked = observability.list_blocked_items("program_1")
    active = observability.list_active_items("program_1")

    assert [item["portfolio_id"] for item in blocked["blocked_portfolios"]] == ["portfolio_blocked"]
    assert [item["goal_id"] for item in blocked["blocked_goals"]] == ["goal_blocked_1", "goal_blocked_2"]
    assert [item["portfolio_id"] for item in active["active_portfolios"]] == ["portfolio_active"]
    assert [item["goal_id"] for item in active["active_goals"]] == ["goal_active"]


def test_summarize_goals_keeps_portfolio_context(tmp_path) -> None:
    observability = _fixture(tmp_path)

    result = observability.summarize_goals("program_1")

    assert result["ok"] is True
    goals_by_id = {item["goal_id"]: item for item in result["goals"]}
    assert goals_by_id["goal_done"]["portfolio_id"] == "portfolio_done"
    assert goals_by_id["goal_blocked_1"]["blocked"] is True
    assert goals_by_id["goal_active"]["active"] is True


def test_observability_is_read_only(tmp_path) -> None:
    observability = _fixture(tmp_path)
    files = [
        tmp_path / "runtime" / "programs" / "programs.json",
        tmp_path / "runtime" / "portfolios" / "portfolios.json",
        tmp_path / "runtime" / "goals" / "goals.json",
    ]
    before = {path: path.read_text(encoding="utf-8") for path in files}

    observability.build_program_tree_summary("program_1")
    observability.summarize_portfolios("program_1")
    observability.summarize_goals("program_1")
    observability.calculate_rollup_metrics("program_1")
    observability.list_blocked_items("program_1")
    observability.list_active_items("program_1")

    after = {path: path.read_text(encoding="utf-8") for path in files}
    assert after == before


def test_observability_boundary_imports_only_read_sources() -> None:
    tree = ast.parse(OBSERVABILITY_FILE.read_text(encoding="utf-8"))
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

    forbidden_imports = {
        "EngineeringProgramCycle",
        "EngineeringPortfolioCycle",
        "EngineeringProgramCoordinator",
        "EngineeringPortfolioCoordinator",
        "EngineeringGoalRunner",
        "EngineeringGoalLoop",
        "RuntimeOrchestrator",
        "EngineeringRuntimeOrchestrator",
        "Scheduler",
        "AER",
        "Memory",
        "UI",
        "core.tasks.engineering_program_cycle",
        "core.tasks.engineering_portfolio_cycle",
        "core.tasks.engineering_program_coordinator",
        "core.tasks.engineering_portfolio_coordinator",
        "core.tasks.engineering_goal_runner",
        "core.tasks.engineering_goal_loop",
        "core.tasks.engineering_runtime_orchestrator",
        "core.tasks.scheduler",
        "core.runtime",
        "core.memory",
        "ui",
    }
    required_imports = {
        "EngineeringProgramRepository",
        "EngineeringProgramState",
        "EngineeringPortfolioRepository",
        "EngineeringPortfolioState",
        "EngineeringGoalRepository",
    }
    forbidden_calls = {"run_cycle", "run_until_idle", "run_next_portfolio", "run_next_goal", "run_goal", "run_until_terminal"}
    assert imports.isdisjoint(forbidden_imports)
    assert required_imports.issubset(imports)
    assert calls.isdisjoint(forbidden_calls)
