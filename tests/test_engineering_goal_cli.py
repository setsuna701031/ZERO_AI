from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from cli import goal_cli
import pytest

pytestmark = [pytest.mark.integration]




REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(argv: list[str], tmp_path: Path, monkeypatch, capsys) -> dict:
    monkeypatch.setenv("ZERO_GOAL_STORE", str(tmp_path / "goals.json"))
    handled = goal_cli.try_handle_goal_command(argv, repo_root=REPO_ROOT)
    assert handled is True
    return json.loads(capsys.readouterr().out)


def test_goal_add_saves_goal_through_repository(tmp_path, monkeypatch, capsys) -> None:
    result = _run_cli(["goal", "add", "Build repository"], tmp_path, monkeypatch, capsys)

    assert result["ok"] is True
    assert result["created"] is True
    assert result["goal"]["summary"] == "Build repository"
    assert (tmp_path / "goals.json").is_file()


def test_goal_list_reads_persisted_repository_goals(tmp_path, monkeypatch, capsys) -> None:
    first = _run_cli(["goal", "add", "First goal"], tmp_path, monkeypatch, capsys)
    second = _run_cli(["goal", "add", "Second goal"], tmp_path, monkeypatch, capsys)

    result = _run_cli(["goal", "list"], tmp_path, monkeypatch, capsys)

    assert [goal["goal_id"] for goal in result["goals"]] == [
        first["goal"]["goal_id"],
        second["goal"]["goal_id"],
    ]
    assert [goal["summary"] for goal in result["goals"]] == ["First goal", "Second goal"]


def test_goal_show_reads_single_goal(tmp_path, monkeypatch, capsys) -> None:
    created = _run_cli(["goal", "add", "Show me"], tmp_path, monkeypatch, capsys)

    result = _run_cli(["goal", "show", created["goal"]["goal_id"]], tmp_path, monkeypatch, capsys)

    assert result["ok"] is True
    assert result["goal"]["goal_id"] == created["goal"]["goal_id"]
    assert result["goal"]["summary"] == "Show me"


def test_goal_add_with_no_summary_creates_goal(tmp_path, monkeypatch, capsys) -> None:
    result = _run_cli(["goal", "add"], tmp_path, monkeypatch, capsys)

    assert result["ok"] is True
    assert result["goal"]["summary"] == "Untitled engineering goal"


def test_goal_list_survives_process_restart(tmp_path) -> None:
    store = tmp_path / "goals.json"
    env = {**os.environ, "ZERO_GOAL_STORE": str(store), "PYTHONPATH": str(REPO_ROOT)}
    python = sys.executable

    add = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "goal", "add", "Restart proof"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    created = json.loads(add.stdout)

    listed = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "goal", "list"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(listed.stdout)

    assert payload["goals"][0]["goal_id"] == created["goal"]["goal_id"]
    assert payload["goals"][0]["summary"] == "Restart proof"


def test_goal_cli_run_requires_goal_id(capsys) -> None:
    assert goal_cli.try_handle_goal_command(["goal", "run"], repo_root=REPO_ROOT) is True
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "unknown_goal_command"
