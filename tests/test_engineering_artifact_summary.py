from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from cli import artifact_cli
from core.tasks.engineering_artifact_repository import EngineeringArtifactRepository
from core.tasks.engineering_artifact_state import EngineeringArtifactState
import pytest

pytestmark = [pytest.mark.integration]




REPO_ROOT = Path(__file__).resolve().parents[1]


def _seed(path: Path) -> Path:
    store = path / "artifacts.json"
    repository = EngineeringArtifactRepository(path, storage_path=store)
    repository.create_artifact(
        {
            "artifact_id": "artifact_report",
            "goal_id": "goal_1",
            "portfolio_id": "portfolio_1",
            "program_id": "program_1",
            "artifact_type": "report",
            "artifact_name": "Report",
            "artifact_path": "workspace/report.md",
            "created_at": 10,
        }
    )
    repository.create_artifact(
        {
            "artifact_id": "artifact_log",
            "program_id": "program_1",
            "artifact_type": "log",
            "artifact_name": "Log",
            "artifact_path": "workspace/log.txt",
            "created_at": 20,
        }
    )
    return store


def test_summarize_artifacts_returns_state_metrics_and_records(tmp_path) -> None:
    store = _seed(tmp_path)
    repository = EngineeringArtifactRepository(tmp_path, storage_path=store)

    summary = EngineeringArtifactState(tmp_path, artifact_repository=repository).summarize_artifacts()

    assert summary["ok"] is True
    assert summary["state"] == "active"
    assert summary["artifact_count"] == 2
    assert summary["artifact_types"] == {"report": 1, "log": 1}
    assert summary["latest_artifact"]["artifact_id"] == "artifact_log"
    assert [item["artifact_id"] for item in summary["artifacts"]] == ["artifact_report", "artifact_log"]


def test_artifact_state_and_summary_cli_smoke(tmp_path, monkeypatch, capsys) -> None:
    store = _seed(tmp_path)
    monkeypatch.setenv("ZERO_ARTIFACT_STORE", str(store))

    handled_state = artifact_cli.try_handle_artifact_command(["artifact", "state"], repo_root=REPO_ROOT)
    state_payload = json.loads(capsys.readouterr().out)
    handled_summary = artifact_cli.try_handle_artifact_command(["artifact", "summary"], repo_root=REPO_ROOT)
    summary_payload = json.loads(capsys.readouterr().out)

    assert handled_state is True
    assert handled_summary is True
    assert state_payload["artifact_state"]["state"] == "active"
    assert state_payload["artifact_state"]["artifact_count"] == 2
    assert summary_payload["artifact_summary"]["latest_artifact"]["artifact_id"] == "artifact_log"
    assert [item["artifact_id"] for item in summary_payload["artifact_summary"]["artifacts"]] == ["artifact_report", "artifact_log"]


def test_app_artifact_state_and_summary_process_smoke(tmp_path) -> None:
    store = _seed(tmp_path)
    env = {
        **dict(os.environ),
        "ZERO_ARTIFACT_STORE": str(store),
        "PYTHONPATH": str(REPO_ROOT),
    }

    state = subprocess.run(
        [sys.executable, str(REPO_ROOT / "app.py"), "artifact", "state"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    summary = subprocess.run(
        [sys.executable, str(REPO_ROOT / "app.py"), "artifact", "summary"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    state_payload = json.loads(state.stdout)
    summary_payload = json.loads(summary.stdout)
    assert state_payload["ok"] is True
    assert state_payload["artifact_state"]["artifact_types"] == {"report": 1, "log": 1}
    assert summary_payload["ok"] is True
    assert summary_payload["artifact_summary"]["artifact_count"] == 2
