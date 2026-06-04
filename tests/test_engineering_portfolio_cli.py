from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from cli import goal_cli, portfolio_cli


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_portfolio_cli(argv: list[str], tmp_path: Path, monkeypatch, capsys) -> dict:
    monkeypatch.setenv("ZERO_PORTFOLIO_STORE", str(tmp_path / "portfolios.json"))
    monkeypatch.setenv("ZERO_GOAL_STORE", str(tmp_path / "goals.json"))
    handled = portfolio_cli.try_handle_portfolio_command(argv, repo_root=REPO_ROOT)
    assert handled is True
    return json.loads(capsys.readouterr().out)


def _run_goal_cli(argv: list[str], tmp_path: Path, monkeypatch, capsys) -> dict:
    monkeypatch.setenv("ZERO_PORTFOLIO_STORE", str(tmp_path / "portfolios.json"))
    monkeypatch.setenv("ZERO_GOAL_STORE", str(tmp_path / "goals.json"))
    handled = goal_cli.try_handle_goal_command(argv, repo_root=REPO_ROOT)
    assert handled is True
    return json.loads(capsys.readouterr().out)


def test_portfolio_create_list_and_show(tmp_path, monkeypatch, capsys) -> None:
    created = _run_portfolio_cli(["portfolio", "create", "Core Runtime"], tmp_path, monkeypatch, capsys)
    portfolio_id = created["portfolio"]["portfolio_id"]

    listed = _run_portfolio_cli(["portfolio", "list"], tmp_path, monkeypatch, capsys)
    shown = _run_portfolio_cli(["portfolio", "show", portfolio_id], tmp_path, monkeypatch, capsys)

    assert created["ok"] is True
    assert created["portfolio"]["name"] == "Core Runtime"
    assert listed["portfolios"][0]["portfolio_id"] == portfolio_id
    assert listed["portfolios"][0]["goal_count"] == 0
    assert shown["ok"] is True
    assert shown["portfolio"]["portfolio_id"] == portfolio_id


def test_portfolio_add_goal_requires_existing_goal_and_remove_goal(tmp_path, monkeypatch, capsys) -> None:
    created_portfolio = _run_portfolio_cli(["portfolio", "create", "Goal Set"], tmp_path, monkeypatch, capsys)
    created_goal = _run_goal_cli(["goal", "add", "Build portfolio proof"], tmp_path, monkeypatch, capsys)
    portfolio_id = created_portfolio["portfolio"]["portfolio_id"]
    goal_id = created_goal["goal"]["goal_id"]

    added = _run_portfolio_cli(["portfolio", "add-goal", portfolio_id, goal_id], tmp_path, monkeypatch, capsys)
    missing = _run_portfolio_cli(["portfolio", "add-goal", portfolio_id, "missing_goal"], tmp_path, monkeypatch, capsys)
    removed = _run_portfolio_cli(["portfolio", "remove-goal", portfolio_id, goal_id], tmp_path, monkeypatch, capsys)

    assert added["ok"] is True
    assert added["portfolio"]["goal_ids"] == [goal_id]
    assert missing["ok"] is False
    assert missing["error"] == "goal_not_found"
    assert removed["ok"] is True
    assert removed["portfolio"]["goal_ids"] == []


def test_portfolio_cli_survives_process_restart_with_goal_refs(tmp_path) -> None:
    portfolio_store = tmp_path / "portfolios.json"
    goal_store = tmp_path / "goals.json"
    env = {
        **dict(os.environ),
        "ZERO_PORTFOLIO_STORE": str(portfolio_store),
        "ZERO_GOAL_STORE": str(goal_store),
        "PYTHONPATH": str(REPO_ROOT),
    }
    python = sys.executable

    created_goal = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "goal", "add", "Persisted goal"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    goal_id = json.loads(created_goal.stdout)["goal"]["goal_id"]
    created_portfolio = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "portfolio", "create", "Restart portfolio"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    portfolio_id = json.loads(created_portfolio.stdout)["portfolio"]["portfolio_id"]

    subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "portfolio", "add-goal", portfolio_id, goal_id],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    shown = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "portfolio", "show", portfolio_id],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(shown.stdout)
    assert payload["ok"] is True
    assert payload["portfolio"]["portfolio_id"] == portfolio_id
    assert payload["portfolio"]["goal_ids"] == [goal_id]
