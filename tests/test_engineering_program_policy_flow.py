from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Mapping

from cli import program_cli
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_program_coordinator import EngineeringProgramCoordinator
from core.tasks.engineering_program_repository import EngineeringProgramRepository
import pytest

pytestmark = [pytest.mark.integration]




REPO_ROOT = Path(__file__).resolve().parents[1]
PROGRAM_COORDINATOR_FILE = REPO_ROOT / "core/tasks/engineering_program_coordinator.py"


class SpyProgramPolicy:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def select_next_portfolio(self, portfolio_summaries: list[Mapping[str, Any]]) -> dict[str, Any]:
        self.calls.append([str(item.get("portfolio_id")) for item in portfolio_summaries])
        return {
            "ok": True,
            "decision": "selected",
            "reason": "selected_runnable_portfolio",
            "selected_portfolio_id": "portfolio_2",
            "selected_portfolio": {"portfolio_id": "portfolio_2", "state": "active"},
            "skipped_portfolios": [{"portfolio_id": "portfolio_1", "state": "paused", "reason": "portfolio_paused"}],
            "selection_summary": {"runnable_portfolio_ids": ["portfolio_2"], "policy_spy": True},
        }


def _repos(tmp_path: Path, *, program_store: Path | None = None, portfolio_store: Path | None = None):
    program_repository = EngineeringProgramRepository(tmp_path, storage_path=program_store) if program_store else EngineeringProgramRepository(tmp_path)
    portfolio_repository = EngineeringPortfolioRepository(tmp_path, storage_path=portfolio_store) if portfolio_store else EngineeringPortfolioRepository(tmp_path)
    program_repository.create_program({"program_id": "program_1", "name": "Policy flow"})
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_1", "name": "Paused", "lifecycle_state": "paused"})
    portfolio_repository.create_portfolio({"portfolio_id": "portfolio_2", "name": "Active"})
    program_repository.add_portfolio("program_1", "portfolio_1")
    program_repository.add_portfolio("program_1", "portfolio_2")
    return program_repository, portfolio_repository


def test_program_coordinator_delegates_selection_to_policy(tmp_path) -> None:
    program_repository, portfolio_repository = _repos(tmp_path)
    policy = SpyProgramPolicy()

    selection = EngineeringProgramCoordinator(
        repo_root=tmp_path,
        program_repository=program_repository,
        portfolio_repository=portfolio_repository,
        program_policy=policy,
    ).select_next_portfolio("program_1")

    assert policy.calls == [["portfolio_1", "portfolio_2"]]
    assert selection["ok"] is True
    assert selection["selected_portfolio_id"] == "portfolio_2"
    assert selection["selection_summary"]["policy_spy"] is True
    assert selection["execution_path"]["program_policy_used"] is True


def test_program_coordinator_has_no_embedded_skip_state_set() -> None:
    source = PROGRAM_COORDINATOR_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
            for alias in node.names:
                imports.add(alias.name)
    assert "EngineeringProgramPolicy" in imports
    assert "NON_RUNNABLE_PORTFOLIO_STATES" not in source
    assert "SKIPPED_PORTFOLIO_STATES" not in source
    assert ".select_next_portfolio(" in source


def test_program_run_next_cli_includes_selection_summary(tmp_path, monkeypatch, capsys) -> None:
    program_store = tmp_path / "programs.json"
    portfolio_store = tmp_path / "portfolios.json"
    monkeypatch.setenv("ZERO_PROGRAM_STORE", str(program_store))
    monkeypatch.setenv("ZERO_PORTFOLIO_STORE", str(portfolio_store))
    _repos(tmp_path, program_store=program_store, portfolio_store=portfolio_store)

    handled = program_cli.try_handle_program_command(["program", "run-next", "program_1"], repo_root=REPO_ROOT)
    payload = json.loads(capsys.readouterr().out)

    assert handled is True
    assert payload["program_run"]["selected_portfolio_id"] == "portfolio_2"
    assert payload["program_run"]["selection"]["selection_summary"]["runnable_portfolio_ids"] == ["portfolio_2"]


def test_program_cycle_cli_smoke_keeps_policy_selection(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    program_store = tmp_path / "programs.json"
    portfolio_store = tmp_path / "portfolios.json"
    monkeypatch.setenv("ZERO_PROGRAM_STORE", str(program_store))
    monkeypatch.setenv("ZERO_PORTFOLIO_STORE", str(portfolio_store))
    _repos(tmp_path, program_store=program_store, portfolio_store=portfolio_store)

    handled = program_cli.try_handle_program_command(
        ["program", "cycle", "program_1"],
        repo_root=REPO_ROOT,
    )
    payload = json.loads(capsys.readouterr().out)

    assert handled is True
    run = payload["program_cycle"]["runs"][0]
    assert run["selected_portfolio_id"] == "portfolio_2"
    assert run["selection"]["selection_summary"]["runnable_portfolio_ids"] == ["portfolio_2"]
