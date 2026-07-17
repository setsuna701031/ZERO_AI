from __future__ import annotations

import json
from pathlib import Path

from cli import goal_cli, portfolio_cli
from core.evidence import EvidenceRecord, EvidenceValidator
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_portfolio_coordinator import EngineeringPortfolioCoordinator
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]




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


def test_real_portfolio_run_next_selects_first_runnable_and_delegates_to_goal_loop(tmp_path) -> None:
    portfolio_repository = EngineeringPortfolioRepository(tmp_path)
    goal_repository = EngineeringGoalRepository(tmp_path)
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Runtime portfolio"})
    _save_complete(goal_repository, "goal_done", "Already done")
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
    assert result["loop_result"]["cycles"][0]["adaptive_decision"] == "replan"
    assert result["loop_result"]["stop_reason"] == "replan"
    assert result["loop_result"]["ok"] is False
    assert goal_repository.load_goal("goal_ready")["status"] == "pending"


def test_real_portfolio_cycle_reports_no_runnable_goal_after_complete(tmp_path) -> None:
    portfolio_repository = EngineeringPortfolioRepository(tmp_path)
    goal_repository = EngineeringGoalRepository(tmp_path)
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Runtime portfolio"})
    _save_complete(goal_repository, "goal_done", "Already done")
    portfolio_repository.add_goal_to_portfolio("portfolio_1", "goal_done")

    result = EngineeringPortfolioCoordinator(
        repo_root=tmp_path,
        portfolio_repository=portfolio_repository,
        goal_repository=goal_repository,
    ).run_portfolio_cycle("portfolio_1")

    assert result["ok"] is False
    assert result["stop_reason"] == "no_runnable_goal"
    assert result["run_count"] == 0


def test_portfolio_run_next_and_cycle_cli_smoke(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    portfolio_store = tmp_path / "portfolios.json"
    goal_store = tmp_path / "goals.json"
    monkeypatch.setenv("ZERO_PORTFOLIO_STORE", str(portfolio_store))
    monkeypatch.setenv("ZERO_GOAL_STORE", str(goal_store))

    assert goal_cli.try_handle_goal_command(
        ["goal", "add", "Build demo system"],
        repo_root=REPO_ROOT,
    ) is True
    first_goal_payload = json.loads(capsys.readouterr().out)

    assert goal_cli.try_handle_goal_command(
        ["goal", "add", "Build demo system"],
        repo_root=REPO_ROOT,
    ) is True
    second_goal_payload = json.loads(capsys.readouterr().out)

    first_goal_id = first_goal_payload["goal"]["goal_id"]
    second_goal_id = second_goal_payload["goal"]["goal_id"]

    assert portfolio_cli.try_handle_portfolio_command(
        ["portfolio", "create", "Coordinator smoke"],
        repo_root=REPO_ROOT,
    ) is True
    created_portfolio_payload = json.loads(capsys.readouterr().out)
    portfolio_id = created_portfolio_payload["portfolio"]["portfolio_id"]

    for goal_id in (first_goal_id, second_goal_id):
        assert portfolio_cli.try_handle_portfolio_command(
            ["portfolio", "add-goal", portfolio_id, goal_id],
            repo_root=REPO_ROOT,
        ) is True
        assert json.loads(capsys.readouterr().out)["ok"] is True

    assert portfolio_cli.try_handle_portfolio_command(
        ["portfolio", "run-next", portfolio_id],
        repo_root=REPO_ROOT,
    ) is True
    run_next_payload = json.loads(capsys.readouterr().out)

    assert portfolio_cli.try_handle_portfolio_command(
        ["portfolio", "cycle", portfolio_id],
        repo_root=REPO_ROOT,
    ) is True
    cycle_payload = json.loads(capsys.readouterr().out)

    assert run_next_payload["coordinator_result"]["selected_goal_id"] == first_goal_id
    assert run_next_payload["coordinator_result"]["loop_result"]["cycle_count"] == 1
    assert run_next_payload["coordinator_result"]["loop_result"]["cycles"][0]["adaptive_decision"] == "replan"
    assert cycle_payload["ok"] is True
    assert cycle_payload["cycle_summary"]["runs"][0]["selected_goal_id"] == first_goal_id
    assert cycle_payload["cycle_summary"]["runs"][0]["loop_result"]["stop_reason"] == "replan"
