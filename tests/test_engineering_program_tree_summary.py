from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from cli import program_cli
from core.evidence import EvidenceRecord, EvidenceValidator
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_program_observability import EngineeringProgramObservability
from core.tasks.engineering_program_repository import EngineeringProgramRepository
import pytest

pytestmark = [pytest.mark.integration]




REPO_ROOT = Path(__file__).resolve().parents[1]


def _save_complete(repository, goal_id: str, summary: str) -> None:
    goal = repository.save_goal({"goal_id": goal_id, "summary": summary, "status": "pending"})
    evidence = EvidenceValidator().validate(
        EvidenceRecord("seed-e", goal_id, None, "test", "ok", "now", metadata=goal["goal_lineage"])
    )
    attestation = GoalCompletionAuthority().complete_goal(
        goal_id=goal_id,
        evidence_refs=[evidence],
        all_subgoals_completed=True,
        goal_lineage=goal["goal_lineage"],
    )
    repository.update_goal(goal_id, {"status": "complete"}, completion_attestation=attestation)


def _seed(
    tmp_path: Path,
    *,
    program_store: Path | None = None,
    portfolio_store: Path | None = None,
    goal_store: Path | None = None,
) -> None:
    program_repository = EngineeringProgramRepository(tmp_path, storage_path=program_store)
    portfolio_repository = EngineeringPortfolioRepository(tmp_path, storage_path=portfolio_store)
    goal_repository = EngineeringGoalRepository(tmp_path, storage_path=goal_store)

    program_repository.create_program({"program_id": "program_1", "name": "Tree program"})
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_alpha", "name": "Alpha"})
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_beta", "name": "Beta"})
    program_repository.add_portfolio("program_1", "portfolio_alpha")
    program_repository.add_portfolio("program_1", "portfolio_beta")

    _save_complete(goal_repository, "goal_a", "Ship A")
    goal_repository.save_goal({"goal_id": "goal_b", "summary": "Ship B", "status": "pending"})
    goal_repository.save_goal({"goal_id": "goal_c", "summary": "Ship C", "status": "blocked"})
    portfolio_repository.add_goal_to_portfolio("portfolio_alpha", "goal_a")
    portfolio_repository.add_goal_to_portfolio("portfolio_alpha", "goal_b")
    portfolio_repository.add_goal_to_portfolio("portfolio_beta", "goal_c")


def test_program_tree_summary_outputs_program_portfolio_goal_shape(tmp_path) -> None:
    _seed(tmp_path)
    result = EngineeringProgramObservability(tmp_path).build_program_tree_summary("program_1")

    assert result["ok"] is True
    assert result["program_id"] == "program_1"
    assert result["tree"]["program_id"] == "program_1"
    assert [item["portfolio_id"] for item in result["tree"]["portfolios"]] == ["portfolio_alpha", "portfolio_beta"]
    alpha = result["tree"]["portfolios"][0]
    beta = result["tree"]["portfolios"][1]
    assert alpha["state"] == "active"
    assert [goal["goal_id"] for goal in alpha["goals"]] == ["goal_a", "goal_b"]
    assert beta["state"] == "blocked"
    assert beta["goals"][0]["blocked"] is True
    assert result["goal_count"] == 3
    assert result["completed_goal_count"] == 1
    assert result["blocked_goal_count"] == 1
    assert result["active_goal_count"] == 1
    assert result["completion_ratio"] == 1 / 3


def test_program_tree_cli_smoke(monkeypatch, capsys) -> None:
    class FakeObservability:
        def build_program_tree_summary(self, program_id: str) -> dict:
            return {
                "schema": "zero.engineering_program_observability.tree.v1",
                "ok": True,
                "program_id": program_id,
                "program_state": "active",
                "portfolio_count": 1,
                "goal_count": 1,
                "completed_goal_count": 0,
                "blocked_goal_count": 0,
                "active_goal_count": 1,
                "completion_ratio": 0.0,
                "tree": {
                    "program_id": program_id,
                    "portfolios": [
                        {
                            "portfolio_id": "portfolio_1",
                            "state": "active",
                            "goals": [{"goal_id": "goal_1", "status": "pending"}],
                        }
                    ],
                },
            }

        def calculate_rollup_metrics(self, program_id: str) -> dict:
            return {
                "schema": "zero.engineering_program_observability.v1",
                "ok": True,
                "program_id": program_id,
                "program_state": "active",
                "portfolio_count": 1,
                "completed_portfolio_count": 0,
                "blocked_portfolio_count": 0,
                "active_portfolio_count": 1,
                "goal_count": 1,
                "completed_goal_count": 0,
                "blocked_goal_count": 0,
                "active_goal_count": 1,
                "completion_ratio": 0.0,
                "active_portfolios": [{"portfolio_id": "portfolio_1"}],
                "blocked_portfolios": [],
                "active_goals": [{"goal_id": "goal_1"}],
                "blocked_goals": [],
            }

    fake = FakeObservability()
    monkeypatch.setattr(program_cli, "_program_observability", lambda repo_root: fake)

    handled_tree = program_cli.try_handle_program_command(["program", "tree", "program_1"], repo_root=REPO_ROOT)
    tree_payload = json.loads(capsys.readouterr().out)
    handled_observability = program_cli.try_handle_program_command(["program", "observability", "program_1"], repo_root=REPO_ROOT)
    observability_payload = json.loads(capsys.readouterr().out)

    assert handled_tree is True
    assert handled_observability is True
    assert tree_payload["program_tree"]["tree"]["portfolios"][0]["goals"][0]["goal_id"] == "goal_1"
    assert observability_payload["program_observability"]["active_goals"][0]["goal_id"] == "goal_1"


def test_app_program_tree_and_observability_process_smoke(tmp_path) -> None:
    program_store = tmp_path / "programs.json"
    portfolio_store = tmp_path / "portfolios.json"
    goal_store = tmp_path / "goals.json"
    _seed(tmp_path, program_store=program_store, portfolio_store=portfolio_store, goal_store=goal_store)
    env = {
        **dict(os.environ),
        "ZERO_PROGRAM_STORE": str(program_store),
        "ZERO_PORTFOLIO_STORE": str(portfolio_store),
        "ZERO_GOAL_STORE": str(goal_store),
        "PYTHONPATH": str(REPO_ROOT),
    }

    tree = subprocess.run(
        [sys.executable, str(REPO_ROOT / "app.py"), "program", "tree", "program_1"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    observability = subprocess.run(
        [sys.executable, str(REPO_ROOT / "app.py"), "program", "observability", "program_1"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    tree_payload = json.loads(tree.stdout)
    observability_payload = json.loads(observability.stdout)
    assert tree_payload["ok"] is True
    assert tree_payload["program_tree"]["tree"]["portfolios"][0]["goals"][0]["goal_id"] == "goal_a"
    assert observability_payload["ok"] is True
    assert observability_payload["program_observability"]["blocked_goals"][0]["goal_id"] == "goal_c"
    assert observability_payload["program_observability"]["completion_ratio"] == 1 / 3
