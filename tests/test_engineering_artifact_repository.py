from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_artifact_repository import EngineeringArtifactRepository


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_REPOSITORY_FILE = REPO_ROOT / "core/tasks/engineering_artifact_repository.py"


def test_create_get_list_and_delete_artifact_records(tmp_path) -> None:
    repository = EngineeringArtifactRepository(tmp_path)

    artifact = repository.create_artifact(
        {
            "artifact_id": "artifact_1",
            "goal_id": "goal_1",
            "portfolio_id": "portfolio_1",
            "program_id": "program_1",
            "artifact_type": "report",
            "artifact_name": "Summary report",
            "artifact_path": "workspace/reports/summary.md",
            "metadata": {"format": "markdown"},
        }
    )

    assert artifact["artifact_id"] == "artifact_1"
    assert artifact["goal_id"] == "goal_1"
    assert artifact["portfolio_id"] == "portfolio_1"
    assert artifact["program_id"] == "program_1"
    assert artifact["artifact_type"] == "report"
    assert artifact["artifact_name"] == "Summary report"
    assert artifact["artifact_path"] == "workspace/reports/summary.md"
    assert artifact["metadata"] == {"format": "markdown"}
    assert (tmp_path / "runtime" / "artifacts" / "artifacts.json").is_file()

    assert repository.get_artifact("artifact_1")["artifact_name"] == "Summary report"
    assert [item["artifact_id"] for item in repository.list_goal_artifacts("goal_1")] == ["artifact_1"]
    assert [item["artifact_id"] for item in repository.list_portfolio_artifacts("portfolio_1")] == ["artifact_1"]
    assert [item["artifact_id"] for item in repository.list_program_artifacts("program_1")] == ["artifact_1"]
    assert repository.list_goal_artifacts("missing") == []

    deleted = repository.delete_artifact("artifact_1")
    assert deleted["ok"] is True
    assert deleted["deleted"] is True
    assert repository.get_artifact("artifact_1") is None
    assert repository.delete_artifact("artifact_1")["reason"] == "artifact_not_found"


def test_create_artifact_generates_id_and_preserves_metadata(tmp_path) -> None:
    repository = EngineeringArtifactRepository(tmp_path)

    artifact = repository.create_artifact(
        {
            "goal_id": "goal_1",
            "artifact_type": "log",
            "artifact_name": "Execution log",
            "artifact_path": "workspace/logs/execution.txt",
            "metadata": {"source": "manual"},
        }
    )

    assert artifact["artifact_id"].startswith("artifact_execution_log_")
    assert artifact["metadata"]["source"] == "manual"
    assert repository.get_artifact(artifact["artifact_id"]) == artifact


def test_artifact_repository_boundary_imports_only_data_layer() -> None:
    tree = ast.parse(ARTIFACT_REPOSITORY_FILE.read_text(encoding="utf-8"))
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
        "RuntimeOrchestrator",
        "EngineeringRuntimeOrchestrator",
        "Scheduler",
        "GoalLoop",
        "EngineeringGoalLoop",
        "GoalRunner",
        "EngineeringGoalRunner",
        "AER",
        "Memory",
        "UI",
        "core.runtime",
        "core.tasks.scheduler",
        "core.tasks.engineering_runtime_orchestrator",
        "core.tasks.engineering_goal_loop",
        "core.tasks.engineering_goal_runner",
        "core.memory",
        "ui",
    }
    assert imports.isdisjoint(forbidden)
