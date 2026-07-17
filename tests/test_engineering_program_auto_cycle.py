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


class FakeProgramCycle:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def run_until_idle(self, program_id: str, max_portfolios: int = 5) -> dict:
        self.calls.append((program_id, max_portfolios))
        return {
            "schema": "zero.engineering_program_cycle.summary.v1",
            "ok": True,
            "program_id": program_id,
            "stop_reason": "program_completed",
            "max_portfolios": max_portfolios,
            "cycle_count": 2,
            "executed_portfolio_count": 2,
            "completed_portfolio_count": 2,
            "blocked_portfolio_count": 0,
            "skipped_portfolio_count": 1,
            "runs": [{"selected_portfolio_id": "portfolio_1"}, {"selected_portfolio_id": "portfolio_2"}],
            "program_state": {"state": "completed", "completed_portfolio_count": 2},
        }


def test_program_run_until_idle_cli_smoke(monkeypatch, capsys) -> None:
    fake_cycle = FakeProgramCycle()
    monkeypatch.setattr(program_cli, "_program_cycle", lambda repo_root: fake_cycle)

    handled = program_cli.try_handle_program_command(["program", "run-until-idle", "program_1"], repo_root=REPO_ROOT)
    payload = json.loads(capsys.readouterr().out)

    assert handled is True
    assert payload["ok"] is True
    assert payload["program_cycle"]["cycle_count"] == 2
    assert payload["program_cycle"]["executed_portfolio_count"] == 2
    assert payload["program_cycle"]["completed_portfolio_count"] == 2
    assert payload["program_cycle"]["blocked_portfolio_count"] == 0
    assert payload["program_cycle"]["skipped_portfolio_count"] == 1
    assert payload["program_cycle"]["max_portfolios"] == 5
    assert fake_cycle.calls == [("program_1", 5)]


def test_program_run_until_idle_cli_accepts_max_portfolios(monkeypatch, capsys) -> None:
    fake_cycle = FakeProgramCycle()
    monkeypatch.setattr(program_cli, "_program_cycle", lambda repo_root: fake_cycle)

    handled = program_cli.try_handle_program_command(["program", "run-until-idle", "program_1", "2"], repo_root=REPO_ROOT)
    payload = json.loads(capsys.readouterr().out)

    assert handled is True
    assert payload["program_cycle"]["max_portfolios"] == 2
    assert fake_cycle.calls == [("program_1", 2)]


def test_app_program_run_until_idle_process_smoke(tmp_path) -> None:
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

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "app.py"), "program", "run-until-idle", "program_1", "1"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["program_cycle"]["cycle_count"] == 1
    assert payload["program_cycle"]["executed_portfolio_count"] == 1
    assert payload["program_cycle"]["runs"][0]["selected_portfolio_id"] == "portfolio_1"
