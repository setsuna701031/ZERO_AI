from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_evidence_repository import EngineeringEvidenceRepository


REPO_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_FILE = REPO_ROOT / "core/tasks/engineering_evidence_repository.py"


def test_create_get_list_scope_and_delete_evidence_records(tmp_path) -> None:
    repository = EngineeringEvidenceRepository(tmp_path)

    evidence = repository.create_evidence(
        {
            "evidence_id": "evidence_1",
            "artifact_id": "artifact_1",
            "goal_id": "goal_1",
            "portfolio_id": "portfolio_1",
            "program_id": "program_1",
            "evidence_type": "test",
            "evidence_name": "Test output",
            "evidence_path": "workspace/test-output.txt",
            "metadata": {"format": "text"},
        }
    )

    assert evidence["evidence_id"] == "evidence_1"
    assert evidence["artifact_id"] == "artifact_1"
    assert evidence["goal_id"] == "goal_1"
    assert evidence["portfolio_id"] == "portfolio_1"
    assert evidence["program_id"] == "program_1"
    assert evidence["evidence_type"] == "test"
    assert evidence["evidence_name"] == "Test output"
    assert evidence["evidence_path"] == "workspace/test-output.txt"
    assert evidence["metadata"] == {"format": "text"}
    assert (tmp_path / "runtime" / "evidence" / "evidence.json").is_file()

    assert repository.get_evidence("evidence_1")["evidence_name"] == "Test output"
    assert [item["evidence_id"] for item in repository.list_evidence()] == ["evidence_1"]
    assert [item["evidence_id"] for item in repository.list_artifact_evidence("artifact_1")] == ["evidence_1"]
    assert [item["evidence_id"] for item in repository.list_goal_evidence("goal_1")] == ["evidence_1"]
    assert [item["evidence_id"] for item in repository.list_portfolio_evidence("portfolio_1")] == ["evidence_1"]
    assert [item["evidence_id"] for item in repository.list_program_evidence("program_1")] == ["evidence_1"]
    assert repository.list_goal_evidence("missing") == []

    deleted = repository.delete_evidence("evidence_1")
    assert deleted["ok"] is True
    assert deleted["deleted"] is True
    assert repository.get_evidence("evidence_1") is None
    assert repository.delete_evidence("evidence_1")["reason"] == "evidence_not_found"


def test_create_evidence_generates_id_and_preserves_metadata(tmp_path) -> None:
    repository = EngineeringEvidenceRepository(tmp_path)

    evidence = repository.create_evidence(
        {
            "goal_id": "goal_1",
            "evidence_type": "log",
            "evidence_name": "Execution log",
            "evidence_path": "workspace/logs/execution.txt",
            "metadata": {"source": "manual"},
        }
    )

    assert evidence["evidence_id"].startswith("evidence_execution_log_")
    assert evidence["metadata"]["source"] == "manual"
    assert repository.get_evidence(evidence["evidence_id"]) == evidence


def test_evidence_repository_boundary_imports_only_data_layer() -> None:
    tree = ast.parse(REPOSITORY_FILE.read_text(encoding="utf-8"))
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
