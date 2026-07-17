from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from cli import program_cli
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_program_repository import EngineeringProgramRepository
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]




REPO_ROOT = Path(__file__).resolve().parents[1]


def test_program_selection_with_real_repositories_uses_first_active_portfolio(tmp_path) -> None:
    program_repository = EngineeringProgramRepository(tmp_path)
    portfolio_repository = EngineeringPortfolioRepository(tmp_path)
    program_repository.create_program({"program_id": "program_1", "name": "Program"})
    portfolio_repository.create_portfolio({"portfolio_id": "paused", "name": "Paused", "lifecycle_state": "paused"})
    portfolio_repository.create_portfolio({"portfolio_id": "active", "name": "Active"})
    program_repository.add_portfolio("program_1", "paused")
    program_repository.add_portfolio("program_1", "active")

    from core.tasks.engineering_program_coordinator import EngineeringProgramCoordinator

    selection = EngineeringProgramCoordinator(
        repo_root=tmp_path,
        program_repository=program_repository,
        portfolio_repository=portfolio_repository,
    ).select_next_portfolio("program_1")

    assert selection["ok"] is True
    assert selection["selected_portfolio_id"] == "active"
    assert selection["skipped_portfolios"][0]["reason"] == "portfolio_paused"


def test_program_cli_run_next_and_cycle_smoke(tmp_path, monkeypatch, capsys) -> None:
    program_store = tmp_path / "programs.json"
    portfolio_store = tmp_path / "portfolios.json"
    monkeypatch.setenv("ZERO_PROGRAM_STORE", str(program_store))
    monkeypatch.setenv("ZERO_PORTFOLIO_STORE", str(portfolio_store))

    program_repository = EngineeringProgramRepository(tmp_path, storage_path=program_store)
    portfolio_repository = EngineeringPortfolioRepository(tmp_path, storage_path=portfolio_store)
    program_repository.create_program({"program_id": "program_1", "name": "Program"})
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Active portfolio"})
    program_repository.add_portfolio("program_1", "portfolio_1")

    handled = program_cli.try_handle_program_command(["program", "run-next", "program_1"], repo_root=REPO_ROOT)
    run_next = json.loads(capsys.readouterr().out)
    handled_cycle = program_cli.try_handle_program_command(["program", "cycle", "program_1"], repo_root=REPO_ROOT)
    cycle = json.loads(capsys.readouterr().out)

    assert handled is True
    assert handled_cycle is True
    assert run_next["program_run"]["selected_portfolio_id"] == "portfolio_1"
    assert run_next["program_run"]["cycle_result"]["portfolio_id"] == "portfolio_1"
    assert cycle["program_cycle"]["runs"][0]["selected_portfolio_id"] == "portfolio_1"


def test_program_cli_outputs_no_runnable_portfolio(tmp_path, monkeypatch, capsys) -> None:
    program_store = tmp_path / "programs.json"
    portfolio_store = tmp_path / "portfolios.json"
    monkeypatch.setenv("ZERO_PROGRAM_STORE", str(program_store))
    monkeypatch.setenv("ZERO_PORTFOLIO_STORE", str(portfolio_store))

    program_repository = EngineeringProgramRepository(tmp_path, storage_path=program_store)
    portfolio_repository = EngineeringPortfolioRepository(tmp_path, storage_path=portfolio_store)
    program_repository.create_program({"program_id": "program_1", "name": "Program"})
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Paused portfolio", "lifecycle_state": "paused"})
    program_repository.add_portfolio("program_1", "portfolio_1")

    handled = program_cli.try_handle_program_command(["program", "run-next", "program_1"], repo_root=REPO_ROOT)
    payload = json.loads(capsys.readouterr().out)

    assert handled is True
    assert payload["ok"] is False
    assert payload["program_run"]["reason"] == "no_runnable_portfolio"


def test_app_program_run_next_and_cycle_process_smoke(tmp_path) -> None:
    program_store = tmp_path / "programs.json"
    portfolio_store = tmp_path / "portfolios.json"
    env = {
        **dict(os.environ),
        "ZERO_PROGRAM_STORE": str(program_store),
        "ZERO_PORTFOLIO_STORE": str(portfolio_store),
        "PYTHONPATH": str(REPO_ROOT),
    }
    program_repository = EngineeringProgramRepository(tmp_path, storage_path=program_store)
    portfolio_repository = EngineeringPortfolioRepository(tmp_path, storage_path=portfolio_store)
    program_repository.create_program({"program_id": "program_1", "name": "Program"})
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Active portfolio"})
    program_repository.add_portfolio("program_1", "portfolio_1")

    python = sys.executable
    run_next = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "program", "run-next", "program_1"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    cycle = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "program", "cycle", "program_1"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    run_next_payload = json.loads(run_next.stdout)
    cycle_payload = json.loads(cycle.stdout)
    assert run_next_payload["program_run"]["selected_portfolio_id"] == "portfolio_1"
    assert cycle_payload["program_cycle"]["runs"][0]["selected_portfolio_id"] == "portfolio_1"
