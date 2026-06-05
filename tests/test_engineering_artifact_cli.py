from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from cli import artifact_cli
from core.tasks.engineering_artifact_repository import EngineeringArtifactRepository


REPO_ROOT = Path(__file__).resolve().parents[1]


def _seed(path: Path) -> None:
    repository = EngineeringArtifactRepository(path, storage_path=path / "artifacts.json")
    repository.create_artifact(
        {
            "artifact_id": "artifact_goal",
            "goal_id": "goal_1",
            "portfolio_id": "portfolio_1",
            "program_id": "program_1",
            "artifact_type": "report",
            "artifact_name": "Goal report",
            "artifact_path": "workspace/goal-report.md",
        }
    )
    repository.create_artifact(
        {
            "artifact_id": "artifact_program",
            "goal_id": "goal_2",
            "portfolio_id": "portfolio_2",
            "program_id": "program_1",
            "artifact_type": "log",
            "artifact_name": "Program log",
            "artifact_path": "workspace/program-log.txt",
        }
    )


def test_artifact_cli_list_and_show_smoke(tmp_path, monkeypatch, capsys) -> None:
    _seed(tmp_path)
    monkeypatch.setenv("ZERO_ARTIFACT_STORE", str(tmp_path / "artifacts.json"))

    handled_goal = artifact_cli.try_handle_artifact_command(["artifact", "list-goal", "goal_1"], repo_root=REPO_ROOT)
    goal_payload = json.loads(capsys.readouterr().out)
    handled_portfolio = artifact_cli.try_handle_artifact_command(["artifact", "list-portfolio", "portfolio_1"], repo_root=REPO_ROOT)
    portfolio_payload = json.loads(capsys.readouterr().out)
    handled_program = artifact_cli.try_handle_artifact_command(["artifact", "list-program", "program_1"], repo_root=REPO_ROOT)
    program_payload = json.loads(capsys.readouterr().out)
    handled_show = artifact_cli.try_handle_artifact_command(["artifact", "show", "artifact_goal"], repo_root=REPO_ROOT)
    show_payload = json.loads(capsys.readouterr().out)

    assert handled_goal is True
    assert handled_portfolio is True
    assert handled_program is True
    assert handled_show is True
    assert [item["artifact_id"] for item in goal_payload["artifacts"]] == ["artifact_goal"]
    assert [item["artifact_id"] for item in portfolio_payload["artifacts"]] == ["artifact_goal"]
    assert [item["artifact_id"] for item in program_payload["artifacts"]] == ["artifact_goal", "artifact_program"]
    assert show_payload["artifact"]["artifact_name"] == "Goal report"


def test_artifact_cli_show_missing_is_not_ok(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ZERO_ARTIFACT_STORE", str(tmp_path / "artifacts.json"))

    handled = artifact_cli.try_handle_artifact_command(["artifact", "show", "missing"], repo_root=REPO_ROOT)
    payload = json.loads(capsys.readouterr().out)

    assert handled is True
    assert payload["ok"] is False
    assert payload["artifact"] == {}


def test_app_artifact_process_smoke(tmp_path) -> None:
    _seed(tmp_path)
    env = {
        **dict(os.environ),
        "ZERO_ARTIFACT_STORE": str(tmp_path / "artifacts.json"),
        "PYTHONPATH": str(REPO_ROOT),
    }

    list_program = subprocess.run(
        [sys.executable, str(REPO_ROOT / "app.py"), "artifact", "list-program", "program_1"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    show = subprocess.run(
        [sys.executable, str(REPO_ROOT / "app.py"), "artifact", "show", "artifact_goal"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    list_payload = json.loads(list_program.stdout)
    show_payload = json.loads(show.stdout)
    assert list_payload["ok"] is True
    assert [item["artifact_id"] for item in list_payload["artifacts"]] == ["artifact_goal", "artifact_program"]
    assert show_payload["ok"] is True
    assert show_payload["artifact"]["artifact_id"] == "artifact_goal"
