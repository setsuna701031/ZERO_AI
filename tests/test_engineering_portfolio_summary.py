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


def _portfolio_with_goals(tmp_path: Path, statuses: dict[str, str]):
    portfolio_repository = EngineeringPortfolioRepository(tmp_path)
    goal_repository = EngineeringGoalRepository(tmp_path)
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Summary portfolio"})
    for goal_id, status in statuses.items():
        goal_repository.save_goal({"goal_id": goal_id, "summary": goal_id, "status": status})
        portfolio_repository.add_goal_to_portfolio("portfolio_1", goal_id)
    return portfolio_repository, goal_repository


def test_summary_exposes_state_and_progress_counts(tmp_path) -> None:
    portfolio_repository, goal_repository = _portfolio_with_goals(
        tmp_path,
        {"goal_done": "complete", "goal_blocked": "blocked", "goal_active": "pending"},
    )

    summary = EngineeringPortfolioCoordinator(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
    ).summarize_portfolio_state("portfolio_1")

    assert summary["ok"] is True
    assert summary["state"] == "active"
    assert summary["progress"] == {
        "goal_count": 3,
        "completed_goal_count": 1,
        "blocked_goal_count": 1,
        "active_goal_count": 1,
        "completion_ratio": 1 / 3,
    }
    assert summary["portfolio_summary"]["goal_count"] == 3
    assert summary["portfolio_summary"]["completed_goal_count"] == 1
    assert summary["portfolio_summary"]["blocked_goal_count"] == 1
    assert summary["portfolio_summary"]["active_goal_count"] == 1
    assert summary["portfolio_summary"]["completion_ratio"] == 1 / 3


def test_read_portfolio_state_returns_compact_state_payload(tmp_path) -> None:
    portfolio_repository, goal_repository = _portfolio_with_goals(tmp_path, {"goal_done": "complete"})

    state = EngineeringPortfolioCoordinator(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
    ).read_portfolio_state("portfolio_1")

    assert state["ok"] is True
    assert state["state"] == "completed"
    assert state["goal_count"] == 1
    assert state["completed_goal_count"] == 1
    assert state["blocked_goal_count"] == 0
    assert state["active_goal_count"] == 0
    assert state["completion_ratio"] == 1.0


def test_portfolio_state_and_summary_cli_smoke(tmp_path) -> None:
    portfolio_store = tmp_path / "portfolios.json"
    goal_store = tmp_path / "goals.json"
    env = {
        **dict(os.environ),
        "ZERO_PORTFOLIO_STORE": str(portfolio_store),
        "ZERO_GOAL_STORE": str(goal_store),
        "PYTHONPATH": str(REPO_ROOT),
    }
    python = sys.executable

    goal = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "goal", "add", "CLI summary goal"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    goal_id = json.loads(goal.stdout)["goal"]["goal_id"]
    portfolio = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "portfolio", "create", "CLI summary portfolio"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    portfolio_id = json.loads(portfolio.stdout)["portfolio"]["portfolio_id"]
    subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "portfolio", "add-goal", portfolio_id, goal_id],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    state = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "portfolio", "state", portfolio_id],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    summary = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "portfolio", "summary", portfolio_id],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    state_payload = json.loads(state.stdout)
    summary_payload = json.loads(summary.stdout)

    assert state_payload["ok"] is True
    assert state_payload["portfolio_state"]["state"] == "active"
    assert state_payload["portfolio_state"]["goal_count"] == 1
    assert state_payload["portfolio_state"]["active_goal_count"] == 1
    assert summary_payload["ok"] is True
    assert summary_payload["portfolio_summary"]["state"] == "active"
    assert summary_payload["portfolio_summary"]["goal_count"] == 1
    assert summary_payload["portfolio_summary"]["completed_goal_count"] == 0
    assert summary_payload["portfolio_summary"]["blocked_goal_count"] == 0
    assert summary_payload["portfolio_summary"]["active_goal_count"] == 1
    assert summary_payload["portfolio_summary"]["completion_ratio"] == 0.0
