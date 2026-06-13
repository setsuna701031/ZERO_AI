from __future__ import annotations

import ast
from pathlib import Path

from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_portfolio_cycle import EngineeringPortfolioCycle
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_program_cycle import EngineeringProgramCycle
from core.tasks.engineering_program_repository import EngineeringProgramRepository


REPO_ROOT = Path(__file__).resolve().parents[1]


class DecisionRunner:
    def __init__(self, decisions: dict[str, str]) -> None:
        self.decisions = decisions
        self.calls: list[str] = []

    def run_goal(self, goal_id: str) -> dict:
        self.calls.append(goal_id)
        decision = self.decisions.get(goal_id, "complete")
        adaptive_decision = {
            "decision": decision,
            "reason": f"{decision}_reason",
            "confidence": 0.9,
            "continuation_plan": {},
            "replan_request": {},
            "blocking_issues": [],
            "root_cause": {"stop_reason": "blocked_dependency"} if decision == "blocked" else {},
        }
        if decision == "complete":
            adaptive_decision["goal_completion_authority_result"] = GoalCompletionAuthority().complete_goal(
                goal_id=goal_id,
                evidence_refs=[{"evidence_id": f"{goal_id}-evidence", "validation_state": "validated"}],
                all_subgoals_completed=True,
            ).to_dict()
        return {
            "ok": decision == "complete",
            "goal_id": goal_id,
            "runtime_result": {"state": decision},
            "adaptive_decision": adaptive_decision,
        }


def test_program_advances_multiple_portfolios_and_reports_blocked_path(tmp_path) -> None:
    goal_repository = EngineeringGoalRepository(tmp_path)
    portfolio_repository = EngineeringPortfolioRepository(tmp_path)
    program_repository = EngineeringProgramRepository(tmp_path)

    for goal_id, status in (
        ("portfolio_1_blocked", "pending"),
        ("portfolio_2_done", "complete"),
        ("portfolio_2_ready", "pending"),
    ):
        goal_repository.save_goal({"goal_id": goal_id, "summary": goal_id, "status": status})

    portfolio_repository.create_portfolio(
        {"portfolio_id": "portfolio_1", "name": "Blocked path", "goal_ids": ["portfolio_1_blocked"]}
    )
    portfolio_repository.create_portfolio(
        {
            "portfolio_id": "portfolio_2",
            "name": "Runnable path",
            "goal_ids": ["portfolio_2_done", "portfolio_2_ready"],
        }
    )
    program_repository.create_program(
        {
            "program_id": "program_1",
            "name": "Closure program",
            "portfolio_ids": ["portfolio_1", "portfolio_2"],
        }
    )

    runner = DecisionRunner({"portfolio_1_blocked": "blocked", "portfolio_2_ready": "complete"})
    goal_loop = EngineeringGoalLoop(repo_root=tmp_path, repository=goal_repository, runner=runner)
    portfolio_cycle = EngineeringPortfolioCycle(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
        goal_loop=goal_loop,
    )
    result = EngineeringProgramCycle(
        repo_root=tmp_path,
        program_repository=program_repository,
        portfolio_repository=portfolio_repository,
        portfolio_cycle=portfolio_cycle,
    ).run_until_idle("program_1", max_portfolios=3)

    assert runner.calls == ["portfolio_1_blocked", "portfolio_2_ready"]
    assert "portfolio_2_done" not in runner.calls
    assert [run["portfolio_id"] for run in result["runs"]] == ["portfolio_1", "portfolio_2"]
    assert result["runs"][0]["stop_reason"] == "portfolio_blocked"
    assert result["runs"][0]["adaptive_decision"]["decision"] == "blocked"
    assert result["runs"][1]["adaptive_decision"]["decision"] == "complete"
    assert result["stop_reason"] == "program_blocked"
    assert result["program_id"] == "program_1"
    assert result["portfolio_id"] == "portfolio_2"
    assert result["goal_id"] == "portfolio_2_ready"
    assert result["selected_goal"]["selected_goal_id"] == "portfolio_2_ready"
    assert result["adaptive_decision"]["decision"] == "complete"
    assert result["completed_count"] == 1
    assert result["blocked_count"] == 1
    assert result["remaining_count"] == 0
    assert result["execution_path"]["route"] == "Program -> Portfolio -> Goal -> Adaptive Planner -> Runtime"
    assert result["execution_path"]["program_owns_strategic_sequencing"] is True
    assert result["execution_path"]["portfolio_owns_goal_selection"] is True
    assert result["execution_path"]["goal_owns_adaptive_continuation"] is True
    assert result["execution_path"]["adaptive_planner_decides_only"] is True
    assert result["execution_path"]["runtime_owns_execution"] is True
    assert portfolio_repository.load_portfolio("portfolio_1")["lifecycle_state"] == "blocked"
    assert portfolio_repository.load_portfolio("portfolio_2")["lifecycle_state"] == "completed"


def test_closure_layers_do_not_import_forbidden_lower_owners() -> None:
    forbidden_by_file = {
        "core/tasks/engineering_program_cycle.py": {
            "EngineeringGoalLoop",
            "EngineeringAdaptivePlanner",
            "EngineeringRuntimeOrchestrator",
            "EngineeringTaskRunner",
        },
        "core/tasks/engineering_portfolio_cycle.py": {
            "EngineeringAdaptivePlanner",
            "EngineeringRuntimeOrchestrator",
            "EngineeringTaskRunner",
        },
        "core/tasks/engineering_goal_loop.py": {
            "EngineeringAdaptivePlanner",
            "EngineeringRuntimeOrchestrator",
            "EngineeringTaskRunner",
        },
    }

    for relative_path, forbidden in forbidden_by_file.items():
        tree = ast.parse((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert imports.isdisjoint(forbidden)
