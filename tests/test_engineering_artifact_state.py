from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_artifact_repository import EngineeringArtifactRepository
from core.tasks.engineering_artifact_state import EngineeringArtifactState


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_STATE_FILE = REPO_ROOT / "core/tasks/engineering_artifact_state.py"


def test_empty_artifact_store_evaluates_empty(tmp_path) -> None:
    state = EngineeringArtifactState(tmp_path)

    result = state.evaluate_artifact_state()

    assert result["state"] == "empty"
    assert result["artifact_count"] == 0
    assert result["artifact_types"] == {}
    assert result["latest_artifact"] == {}


def test_artifact_metrics_count_scopes_types_and_latest(tmp_path) -> None:
    repository = EngineeringArtifactRepository(tmp_path)
    repository.create_artifact(
        {
            "artifact_id": "artifact_1",
            "goal_id": "goal_1",
            "portfolio_id": "portfolio_1",
            "program_id": "program_1",
            "artifact_type": "report",
            "artifact_name": "Report",
            "created_at": 10,
        }
    )
    repository.create_artifact(
        {
            "artifact_id": "artifact_2",
            "program_id": "program_1",
            "artifact_type": "log",
            "artifact_name": "Log",
            "created_at": 20,
        }
    )
    repository.create_artifact(
        {
            "artifact_id": "artifact_3",
            "portfolio_id": "portfolio_2",
            "artifact_type": "report",
            "artifact_name": "Portfolio report",
            "created_at": 15,
        }
    )

    result = EngineeringArtifactState(tmp_path, artifact_repository=repository).evaluate_artifact_state()

    assert result["state"] == "active"
    assert result["artifact_count"] == 3
    assert result["goal_artifact_count"] == 1
    assert result["portfolio_artifact_count"] == 2
    assert result["program_artifact_count"] == 2
    assert result["artifact_types"] == {"report": 2, "log": 1}
    assert result["latest_artifact"]["artifact_id"] == "artifact_2"


def test_all_archived_artifacts_evaluate_archived(tmp_path) -> None:
    repository = EngineeringArtifactRepository(tmp_path)
    repository.create_artifact(
        {
            "artifact_id": "artifact_1",
            "artifact_name": "Old report",
            "artifact_type": "report",
            "metadata": {"state": "archived"},
        }
    )
    repository.create_artifact(
        {
            "artifact_id": "artifact_2",
            "artifact_name": "Old log",
            "artifact_type": "log",
            "metadata": {"artifact_state": "archived"},
        }
    )

    result = EngineeringArtifactState(tmp_path, artifact_repository=repository).evaluate_artifact_state()

    assert result["state"] == "archived"
    assert result["artifact_count"] == 2


def test_artifact_state_boundary_imports_only_repository() -> None:
    tree = ast.parse(ARTIFACT_STATE_FILE.read_text(encoding="utf-8"))
    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
            for alias in node.names:
                imports.add(alias.name)

    forbidden = {
        "GoalLoop",
        "EngineeringGoalLoop",
        "GoalRunner",
        "EngineeringGoalRunner",
        "RuntimeOrchestrator",
        "EngineeringRuntimeOrchestrator",
        "Scheduler",
        "AER",
        "Memory",
        "UI",
        "core.tasks.engineering_goal_loop",
        "core.tasks.engineering_goal_runner",
        "core.tasks.engineering_runtime_orchestrator",
        "core.tasks.scheduler",
        "core.runtime",
        "core.memory",
        "ui",
    }
    assert imports.isdisjoint(forbidden)
    assert "EngineeringArtifactRepository" in imports
