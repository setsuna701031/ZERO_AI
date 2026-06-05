from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from cli import program_cli


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_program_cli(argv: list[str], tmp_path: Path, monkeypatch, capsys) -> dict:
    monkeypatch.setenv("ZERO_PROGRAM_STORE", str(tmp_path / "programs.json"))
    handled = program_cli.try_handle_program_command(argv, repo_root=REPO_ROOT)
    assert handled is True
    return json.loads(capsys.readouterr().out)


def test_program_create_list_and_show(tmp_path, monkeypatch, capsys) -> None:
    created = _run_program_cli(["program", "create", "Core Runtime Program"], tmp_path, monkeypatch, capsys)
    program_id = created["program"]["program_id"]

    listed = _run_program_cli(["program", "list"], tmp_path, monkeypatch, capsys)
    shown = _run_program_cli(["program", "show", program_id], tmp_path, monkeypatch, capsys)

    assert created["ok"] is True
    assert created["program"]["name"] == "Core Runtime Program"
    assert listed["programs"][0]["program_id"] == program_id
    assert listed["programs"][0]["portfolio_count"] == 0
    assert shown["ok"] is True
    assert shown["program"]["program_id"] == program_id


def test_program_add_and_remove_portfolio_refs(tmp_path, monkeypatch, capsys) -> None:
    created_program = _run_program_cli(["program", "create", "Portfolio Set"], tmp_path, monkeypatch, capsys)
    program_id = created_program["program"]["program_id"]

    added = _run_program_cli(["program", "add-portfolio", program_id, "portfolio_1"], tmp_path, monkeypatch, capsys)
    duplicate = _run_program_cli(["program", "add-portfolio", program_id, "portfolio_1"], tmp_path, monkeypatch, capsys)
    removed = _run_program_cli(["program", "remove-portfolio", program_id, "portfolio_1"], tmp_path, monkeypatch, capsys)

    assert added["ok"] is True
    assert added["program"]["portfolio_ids"] == ["portfolio_1"]
    assert duplicate["program"]["portfolio_ids"] == ["portfolio_1"]
    assert removed["ok"] is True
    assert removed["program"]["portfolio_ids"] == []


def test_program_cli_survives_process_restart_with_portfolio_refs(tmp_path) -> None:
    program_store = tmp_path / "programs.json"
    env = {
        **dict(os.environ),
        "ZERO_PROGRAM_STORE": str(program_store),
        "PYTHONPATH": str(REPO_ROOT),
    }
    python = sys.executable

    created_program = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "program", "create", "Restart program"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    program_id = json.loads(created_program.stdout)["program"]["program_id"]

    subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "program", "add-portfolio", program_id, "portfolio_1"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    shown = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "program", "show", program_id],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(shown.stdout)
    assert payload["ok"] is True
    assert payload["program"]["program_id"] == program_id
    assert payload["program"]["portfolio_ids"] == ["portfolio_1"]
