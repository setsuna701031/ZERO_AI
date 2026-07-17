from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from cli import artifact_cli
from core.tasks.engineering_artifact_repository import EngineeringArtifactRepository
from core.tasks.engineering_artifact_state import EngineeringArtifactState


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_STATE_FILE = REPO_ROOT / "core/tasks/engineering_artifact_state.py"
ARTIFACT_CLI_FILE = REPO_ROOT / "cli/artifact_cli.py"


class SpyArtifactPolicy:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def build_artifact_summary(self, artifacts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        records = [dict(item) for item in artifacts]
        self.calls.append([str(item.get("artifact_id")) for item in records])
        latest = records[-1] if records else {}
        return {
            "schema": "spy.artifact_policy",
            "ok": True,
            "active": records[-1:] if records else [],
            "archived": records[:-1],
            "active_count": 1 if records else 0,
            "archived_count": max(len(records) - 1, 0),
            "artifact_count": len(records),
            "latest_artifact": latest,
            "artifact_type_summary": {
                "spy": {
                    "artifact_type": "spy",
                    "active": 1 if records else 0,
                    "archived": max(len(records) - 1, 0),
                    "total": len(records),
                    "latest_artifact": latest,
                }
            },
        }


def _seed(path: Path, *, store: Path | None = None) -> EngineeringArtifactRepository:
    repository = EngineeringArtifactRepository(path, storage_path=store) if store else EngineeringArtifactRepository(path)
    repository.create_artifact(
        {
            "artifact_id": "artifact_report",
            "artifact_type": "report",
            "artifact_name": "Report",
            "created_at": 10,
            "metadata": {"state": "archived"},
        }
    )
    repository.create_artifact(
        {
            "artifact_id": "artifact_log",
            "artifact_type": "log",
            "artifact_name": "Log",
            "created_at": 20,
        }
    )
    return repository


def test_artifact_state_delegates_summary_rules_to_policy(tmp_path) -> None:
    repository = _seed(tmp_path)
    policy = SpyArtifactPolicy()

    summary = EngineeringArtifactState(tmp_path, artifact_repository=repository, artifact_policy=policy).summarize_artifacts()

    assert policy.calls == [["artifact_report", "artifact_log"]]
    assert summary["state"] == "active"
    assert summary["active_artifact_count"] == 1
    assert summary["archived_artifact_count"] == 1
    assert summary["artifact_type_summary"]["spy"]["total"] == 2
    assert summary["latest_artifact"]["artifact_id"] == "artifact_log"
    assert summary["policy_summary"]["schema"] == "spy.artifact_policy"


def test_artifact_state_uses_policy_to_mark_all_archived(tmp_path) -> None:
    repository = EngineeringArtifactRepository(tmp_path)
    repository.create_artifact({"artifact_id": "artifact_a", "artifact_name": "A", "metadata": {"state": "archived"}})
    repository.create_artifact({"artifact_id": "artifact_b", "artifact_name": "B", "metadata": {"archived": True}})

    result = EngineeringArtifactState(tmp_path, artifact_repository=repository).evaluate_artifact_state()

    assert result["state"] == "archived"
    assert result["policy_summary"]["archived_count"] == 2
    assert result["active_artifact_count"] == 0


def test_artifact_summary_cli_includes_policy_summary(tmp_path, monkeypatch, capsys) -> None:
    store = tmp_path / "artifacts.json"
    _seed(tmp_path, store=store)
    monkeypatch.setenv("ZERO_ARTIFACT_STORE", str(store))

    handled = artifact_cli.try_handle_artifact_command(["artifact", "summary"], repo_root=REPO_ROOT)
    payload = json.loads(capsys.readouterr().out)

    assert handled is True
    assert payload["ok"] is True
    assert payload["policy_summary"]["artifact_type_summary"]["report"]["archived"] == 1
    assert payload["artifact_summary"]["policy_summary"] == payload["policy_summary"]
    assert payload["artifact_summary"]["latest_artifact"]["artifact_id"] == "artifact_log"


def test_artifact_state_and_cli_boundaries_stay_out_of_runtime_goal_scheduler_memory_and_ui() -> None:
    forbidden = {
        "GoalLoop",
        "EngineeringGoalLoop",
        "GoalRunner",
        "EngineeringGoalRunner",
        "RuntimeOrchestrator",
        "EngineeringRuntimeOrchestrator",
        "Scheduler",
        "EngineeringGoalScheduler",
        "AER",
        "Memory",
        "UI",
        "core.tasks.engineering_goal_loop",
        "core.tasks.engineering_goal_runner",
        "core.tasks.engineering_runtime_orchestrator",
        "core.tasks.engineering_goal_scheduler",
        "core.tasks.scheduler",
        "core.runtime",
        "core.memory",
        "ui",
    }

    for path in (ARTIFACT_STATE_FILE, ARTIFACT_CLI_FILE):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
                for alias in node.names:
                    imports.add(alias.name)
        assert imports.isdisjoint(forbidden)

    state_source = ARTIFACT_STATE_FILE.read_text(encoding="utf-8")
    assert "EngineeringArtifactPolicy" in state_source
    assert ".build_artifact_summary(" in state_source
