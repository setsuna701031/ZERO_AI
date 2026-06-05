from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from cli import evidence_cli
from core.tasks.engineering_evidence_repository import EngineeringEvidenceRepository


REPO_ROOT = Path(__file__).resolve().parents[1]


def _seed(path: Path) -> None:
    repository = EngineeringEvidenceRepository(path, storage_path=path / "evidence.json")
    repository.create_evidence(
        {
            "evidence_id": "evidence_goal",
            "artifact_id": "artifact_1",
            "goal_id": "goal_1",
            "portfolio_id": "portfolio_1",
            "program_id": "program_1",
            "evidence_type": "test",
            "evidence_name": "Goal evidence",
            "evidence_path": "workspace/goal-evidence.txt",
        }
    )
    repository.create_evidence(
        {
            "evidence_id": "evidence_program",
            "artifact_id": "artifact_2",
            "goal_id": "goal_2",
            "portfolio_id": "portfolio_2",
            "program_id": "program_1",
            "evidence_type": "log",
            "evidence_name": "Program evidence",
            "evidence_path": "workspace/program-evidence.txt",
        }
    )


def test_evidence_cli_create_list_show_delete_smoke(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ZERO_EVIDENCE_STORE", str(tmp_path / "evidence.json"))

    handled_create = evidence_cli.try_handle_evidence_command(
        [
            "evidence",
            "create",
            "Acceptance proof",
            "--id",
            "evidence_acceptance",
            "--artifact",
            "artifact_1",
            "--goal",
            "goal_1",
            "--portfolio",
            "portfolio_1",
            "--program",
            "program_1",
            "--type",
            "test",
            "--path",
            "workspace/acceptance.txt",
        ],
        repo_root=REPO_ROOT,
    )
    create_payload = json.loads(capsys.readouterr().out)
    handled_list = evidence_cli.try_handle_evidence_command(["evidence", "list"], repo_root=REPO_ROOT)
    list_payload = json.loads(capsys.readouterr().out)
    handled_show = evidence_cli.try_handle_evidence_command(["evidence", "show", "evidence_acceptance"], repo_root=REPO_ROOT)
    show_payload = json.loads(capsys.readouterr().out)
    handled_delete = evidence_cli.try_handle_evidence_command(["evidence", "delete", "evidence_acceptance"], repo_root=REPO_ROOT)
    delete_payload = json.loads(capsys.readouterr().out)

    assert handled_create is True
    assert handled_list is True
    assert handled_show is True
    assert handled_delete is True
    assert create_payload["created"] is True
    assert create_payload["evidence"]["artifact_id"] == "artifact_1"
    assert [item["evidence_id"] for item in list_payload["evidence"]] == ["evidence_acceptance"]
    assert show_payload["evidence"]["evidence_name"] == "Acceptance proof"
    assert delete_payload["evidence_delete"]["deleted"] is True


def test_evidence_cli_scope_state_summary_and_tree_smoke(tmp_path, monkeypatch, capsys) -> None:
    _seed(tmp_path)
    monkeypatch.setenv("ZERO_EVIDENCE_STORE", str(tmp_path / "evidence.json"))

    handled_artifact = evidence_cli.try_handle_evidence_command(["evidence", "list-artifact", "artifact_1"], repo_root=REPO_ROOT)
    artifact_payload = json.loads(capsys.readouterr().out)
    handled_goal = evidence_cli.try_handle_evidence_command(["evidence", "list-goal", "goal_1"], repo_root=REPO_ROOT)
    goal_payload = json.loads(capsys.readouterr().out)
    handled_portfolio = evidence_cli.try_handle_evidence_command(["evidence", "list-portfolio", "portfolio_1"], repo_root=REPO_ROOT)
    portfolio_payload = json.loads(capsys.readouterr().out)
    handled_program = evidence_cli.try_handle_evidence_command(["evidence", "list-program", "program_1"], repo_root=REPO_ROOT)
    program_payload = json.loads(capsys.readouterr().out)
    handled_state = evidence_cli.try_handle_evidence_command(["evidence", "state"], repo_root=REPO_ROOT)
    state_payload = json.loads(capsys.readouterr().out)
    handled_summary = evidence_cli.try_handle_evidence_command(["evidence", "summary"], repo_root=REPO_ROOT)
    summary_payload = json.loads(capsys.readouterr().out)
    handled_tree = evidence_cli.try_handle_evidence_command(["evidence", "tree"], repo_root=REPO_ROOT)
    tree_payload = json.loads(capsys.readouterr().out)

    assert handled_artifact is True
    assert handled_goal is True
    assert handled_portfolio is True
    assert handled_program is True
    assert handled_state is True
    assert handled_summary is True
    assert handled_tree is True
    assert [item["evidence_id"] for item in artifact_payload["evidence"]] == ["evidence_goal"]
    assert [item["evidence_id"] for item in goal_payload["evidence"]] == ["evidence_goal"]
    assert [item["evidence_id"] for item in portfolio_payload["evidence"]] == ["evidence_goal"]
    assert [item["evidence_id"] for item in program_payload["evidence"]] == ["evidence_goal", "evidence_program"]
    assert state_payload["evidence_state"]["state"] == "active"
    assert summary_payload["policy_summary"]["evidence_type_summary"]["test"]["total"] == 1
    assert tree_payload["evidence_tree"]["tree"]["programs"][0]["program_id"] == "program_1"


def test_app_evidence_process_smoke(tmp_path) -> None:
    _seed(tmp_path)
    env = {
        **dict(os.environ),
        "ZERO_EVIDENCE_STORE": str(tmp_path / "evidence.json"),
        "PYTHONPATH": str(REPO_ROOT),
    }

    list_program = subprocess.run(
        [sys.executable, str(REPO_ROOT / "app.py"), "evidence", "list-program", "program_1"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    summary = subprocess.run(
        [sys.executable, str(REPO_ROOT / "app.py"), "evidence", "summary"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    list_payload = json.loads(list_program.stdout)
    summary_payload = json.loads(summary.stdout)
    assert list_payload["ok"] is True
    assert [item["evidence_id"] for item in list_payload["evidence"]] == ["evidence_goal", "evidence_program"]
    assert summary_payload["ok"] is True
    assert summary_payload["evidence_summary"]["evidence_count"] == 2
