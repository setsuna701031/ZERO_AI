from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_evidence_repository import EngineeringEvidenceRepository
from core.tasks.engineering_evidence_state import EngineeringEvidenceState


REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = REPO_ROOT / "core/tasks/engineering_evidence_state.py"


def test_empty_evidence_store_evaluates_empty(tmp_path) -> None:
    result = EngineeringEvidenceState(tmp_path).evaluate_evidence_state()

    assert result["state"] == "empty"
    assert result["evidence_count"] == 0
    assert result["evidence_type_summary"] == {}
    assert result["latest_evidence"] == {}


def test_evidence_metrics_count_scopes_types_and_latest(tmp_path) -> None:
    repository = EngineeringEvidenceRepository(tmp_path)
    repository.create_evidence(
        {
            "evidence_id": "evidence_1",
            "artifact_id": "artifact_1",
            "goal_id": "goal_1",
            "portfolio_id": "portfolio_1",
            "program_id": "program_1",
            "evidence_type": "test",
            "evidence_name": "Test",
            "created_at": 10,
        }
    )
    repository.create_evidence(
        {
            "evidence_id": "evidence_2",
            "program_id": "program_1",
            "evidence_type": "log",
            "evidence_name": "Log",
            "created_at": 20,
        }
    )
    repository.create_evidence(
        {
            "evidence_id": "evidence_3",
            "portfolio_id": "portfolio_2",
            "evidence_type": "test",
            "evidence_name": "Portfolio test",
            "created_at": 15,
        }
    )

    result = EngineeringEvidenceState(tmp_path, evidence_repository=repository).evaluate_evidence_state()

    assert result["state"] == "active"
    assert result["evidence_count"] == 3
    assert result["artifact_evidence_count"] == 1
    assert result["goal_evidence_count"] == 1
    assert result["portfolio_evidence_count"] == 2
    assert result["program_evidence_count"] == 2
    assert result["evidence_types"] == {"test": 2, "log": 1}
    assert result["evidence_type_summary"]["test"]["total"] == 2
    assert result["latest_evidence"]["evidence_id"] == "evidence_2"


def test_all_archived_evidence_evaluates_archived(tmp_path) -> None:
    repository = EngineeringEvidenceRepository(tmp_path)
    repository.create_evidence({"evidence_id": "evidence_1", "evidence_name": "Old test", "metadata": {"state": "archived"}})
    repository.create_evidence({"evidence_id": "evidence_2", "evidence_name": "Old log", "metadata": {"archived": True}})

    result = EngineeringEvidenceState(tmp_path, evidence_repository=repository).evaluate_evidence_state()

    assert result["state"] == "archived"
    assert result["evidence_count"] == 2
    assert result["active_evidence_count"] == 0
    assert result["archived_evidence_count"] == 2


def test_summarize_evidence_returns_state_metrics_records_and_policy_summary(tmp_path) -> None:
    repository = EngineeringEvidenceRepository(tmp_path)
    repository.create_evidence({"evidence_id": "evidence_1", "evidence_name": "Test", "evidence_type": "test", "created_at": 10})
    repository.create_evidence({"evidence_id": "evidence_2", "evidence_name": "Log", "evidence_type": "log", "created_at": 20})

    summary = EngineeringEvidenceState(tmp_path, evidence_repository=repository).summarize_evidence()

    assert summary["ok"] is True
    assert summary["state"] == "active"
    assert summary["evidence_count"] == 2
    assert summary["evidence_types"] == {"test": 1, "log": 1}
    assert summary["latest_evidence"]["evidence_id"] == "evidence_2"
    assert [item["evidence_id"] for item in summary["evidence"]] == ["evidence_1", "evidence_2"]
    assert summary["policy_summary"]["active_count"] == 2


def test_evidence_state_boundary_imports_only_repository_and_policy() -> None:
    tree = ast.parse(STATE_FILE.read_text(encoding="utf-8"))
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
    assert "EngineeringEvidenceRepository" in imports
    assert "EngineeringEvidencePolicy" in imports
