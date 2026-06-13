from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_portfolio_coordinator import EngineeringPortfolioCoordinator
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_real_portfolio_run_next_selects_first_runnable_and_delegates_to_goal_loop(tmp_path) -> None:
    portfolio_repository = EngineeringPortfolioRepository(tmp_path)
    goal_repository = EngineeringGoalRepository(tmp_path)
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Runtime portfolio"})
    goal_repository.save_goal({"goal_id": "goal_done", "summary": "Already done", "status": "complete"})
    goal_repository.save_goal({"goal_id": "goal_ready", "summary": "Build demo system", "status": "pending"})
    portfolio_repository.add_goal_to_portfolio("portfolio_1", "goal_done")
    portfolio_repository.add_goal_to_portfolio("portfolio_1", "goal_ready")

    result = EngineeringPortfolioCoordinator(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
    ).run_next_goal("portfolio_1")

    assert result["selected_goal_id"] == "goal_ready"
    assert result["selection"]["skipped_goals"][0]["goal_id"] == "goal_done"
    assert result["loop_result"]["cycle_count"] == 1
    assert result["loop_result"]["cycles"][0]["adaptive_decision"] in {"complete", "blocked"}
    assert result["loop_result"]["stop_reason"] == "goal_completion_authority_required"
    assert goal_repository.load_goal("goal_ready")["status"] == "pending"


def test_real_portfolio_cycle_reports_no_runnable_goal_after_complete(tmp_path) -> None:
    portfolio_repository = EngineeringPortfolioRepository(tmp_path)
    goal_repository = EngineeringGoalRepository(tmp_path)
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Runtime portfolio"})
    goal_repository.save_goal({"goal_id": "goal_done", "summary": "Already done", "status": "complete"})
    portfolio_repository.add_goal_to_portfolio("portfolio_1", "goal_done")

    result = EngineeringPortfolioCoordinator(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
    ).run_portfolio_cycle("portfolio_1")

    assert result["ok"] is False
    assert result["stop_reason"] == "no_runnable_goal"
    assert result["run_count"] == 0


def test_portfolio_run_next_and_cycle_cli_smoke(tmp_path) -> None:
    portfolio_store = tmp_path / "portfolios.json"
    goal_store = tmp_path / "goals.json"
    env = {
        **dict(os.environ),
        "ZERO_PORTFOLIO_STORE": str(portfolio_store),
        "ZERO_GOAL_STORE": str(goal_store),
        "PYTHONPATH": str(REPO_ROOT),
    }
    python = sys.executable

    first_goal = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "goal", "add", "Build demo system"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    second_goal = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "goal", "add", "Build demo system"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    first_goal_id = json.loads(first_goal.stdout)["goal"]["goal_id"]
    second_goal_id = json.loads(second_goal.stdout)["goal"]["goal_id"]

    created_portfolio = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "portfolio", "create", "Coordinator smoke"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    portfolio_id = json.loads(created_portfolio.stdout)["portfolio"]["portfolio_id"]
    for goal_id in (first_goal_id, second_goal_id):
        subprocess.run(
            [python, str(REPO_ROOT / "app.py"), "portfolio", "add-goal", portfolio_id, goal_id],
            cwd=REPO_ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    run_next = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "portfolio", "run-next", portfolio_id],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    cycle = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "portfolio", "cycle", portfolio_id],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    run_next_payload = json.loads(run_next.stdout)
    cycle_payload = json.loads(cycle.stdout)

    assert run_next_payload["coordinator_result"]["selected_goal_id"] == first_goal_id
    assert run_next_payload["coordinator_result"]["loop_result"]["cycle_count"] == 1
    assert run_next_payload["coordinator_result"]["loop_result"]["cycles"][0]["adaptive_decision"] in {"complete", "blocked"}
    assert cycle_payload["ok"] is True
    assert cycle_payload["cycle_summary"]["runs"][0]["selected_goal_id"] == first_goal_id
    assert (
        cycle_payload["cycle_summary"]["runs"][0]["loop_result"]["stop_reason"]
        == "goal_completion_authority_required"
    )
