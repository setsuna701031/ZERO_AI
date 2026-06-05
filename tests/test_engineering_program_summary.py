from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from cli import program_cli
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_program_repository import EngineeringProgramRepository
from core.tasks.engineering_program_state import EngineeringProgramState


REPO_ROOT = Path(__file__).resolve().parents[1]


def _repos(tmp_path: Path, *, program_store: Path | None = None, portfolio_store: Path | None = None):
    program_repository = EngineeringProgramRepository(tmp_path, storage_path=program_store) if program_store else EngineeringProgramRepository(tmp_path)
    portfolio_repository = EngineeringPortfolioRepository(tmp_path, storage_path=portfolio_store) if portfolio_store else EngineeringPortfolioRepository(tmp_path)
    program_repository.create_program({"program_id": "program_1", "name": "Summary program"})
    for portfolio_id, state in {"done": "completed", "blocked": "blocked", "active": "active"}.items():
        fields = {"portfolio_id": portfolio_id, "name": portfolio_id}
        if state != "active":
            fields["lifecycle_state"] = state
        portfolio_repository.create_portfolio(fields)
        program_repository.add_portfolio("program_1", portfolio_id)
    return program_repository, portfolio_repository


def test_summarize_program_returns_compact_state_and_portfolio_details(tmp_path) -> None:
    program_repository, portfolio_repository = _repos(tmp_path)

    summary = EngineeringProgramState(
        tmp_path,
        program_repository=program_repository,
        portfolio_repository=portfolio_repository,
    ).summarize_program("program_1")

    assert summary["ok"] is True
    assert summary["state"] == "active"
    assert summary["portfolio_count"] == 3
    assert summary["completed_portfolio_count"] == 1
    assert summary["blocked_portfolio_count"] == 1
    assert summary["active_portfolio_count"] == 1
    assert summary["completion_ratio"] == 1 / 3
    assert summary["runnable_portfolio_ids"] == ["active"]
    assert [item["portfolio_id"] for item in summary["skipped_portfolios"]] == ["done", "blocked"]


def test_program_state_and_summary_cli_smoke(tmp_path, monkeypatch, capsys) -> None:
    program_store = tmp_path / "programs.json"
    portfolio_store = tmp_path / "portfolios.json"
    monkeypatch.setenv("ZERO_PROGRAM_STORE", str(program_store))
    monkeypatch.setenv("ZERO_PORTFOLIO_STORE", str(portfolio_store))
    _repos(tmp_path, program_store=program_store, portfolio_store=portfolio_store)

    handled_state = program_cli.try_handle_program_command(["program", "state", "program_1"], repo_root=REPO_ROOT)
    state_payload = json.loads(capsys.readouterr().out)
    handled_summary = program_cli.try_handle_program_command(["program", "summary", "program_1"], repo_root=REPO_ROOT)
    summary_payload = json.loads(capsys.readouterr().out)

    assert handled_state is True
    assert handled_summary is True
    assert state_payload["program_state"]["state"] == "active"
    assert state_payload["program_state"]["portfolio_count"] == 3
    assert summary_payload["program_summary"]["state"] == "active"
    assert summary_payload["program_summary"]["runnable_portfolio_ids"] == ["active"]


def test_app_program_state_and_summary_process_smoke(tmp_path) -> None:
    program_store = tmp_path / "programs.json"
    portfolio_store = tmp_path / "portfolios.json"
    _repos(tmp_path, program_store=program_store, portfolio_store=portfolio_store)
    env = {
        **dict(os.environ),
        "ZERO_PROGRAM_STORE": str(program_store),
        "ZERO_PORTFOLIO_STORE": str(portfolio_store),
        "PYTHONPATH": str(REPO_ROOT),
    }
    python = sys.executable

    state = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "program", "state", "program_1"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    summary = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "program", "summary", "program_1"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    state_payload = json.loads(state.stdout)
    summary_payload = json.loads(summary.stdout)
    assert state_payload["program_state"]["state"] == "active"
    assert summary_payload["program_summary"]["portfolio_count"] == 3
