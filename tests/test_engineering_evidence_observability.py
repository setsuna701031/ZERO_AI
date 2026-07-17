from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_evidence_observability import EngineeringEvidenceObservability
from core.tasks.engineering_evidence_repository import EngineeringEvidenceRepository
from core.tasks.engineering_evidence_state import EngineeringEvidenceState


REPO_ROOT = Path(__file__).resolve().parents[1]
OBSERVABILITY_FILE = REPO_ROOT / "core/tasks/engineering_evidence_observability.py"


def _seed(tmp_path: Path) -> EngineeringEvidenceRepository:
    repository = EngineeringEvidenceRepository(tmp_path)
    repository.create_evidence(
        {
            "evidence_id": "evidence_test",
            "artifact_id": "artifact_1",
            "goal_id": "goal_1",
            "portfolio_id": "portfolio_1",
            "program_id": "program_1",
            "evidence_type": "test",
            "evidence_name": "Test output",
            "created_at": 10,
        }
    )
    repository.create_evidence(
        {
            "evidence_id": "evidence_log",
            "artifact_id": "artifact_2",
            "goal_id": "goal_2",
            "portfolio_id": "portfolio_1",
            "program_id": "program_1",
            "evidence_type": "log",
            "evidence_name": "Log output",
            "created_at": 20,
        }
    )
    return repository


def test_observability_calculates_rollup_metrics_from_state_summary(tmp_path) -> None:
    repository = _seed(tmp_path)
    observability = EngineeringEvidenceObservability(
        tmp_path,
        evidence_repository=repository,
        evidence_state=EngineeringEvidenceState(tmp_path, evidence_repository=repository),
    )

    metrics = observability.calculate_rollup_metrics()

    assert metrics["ok"] is True
    assert metrics["state"] == "active"
    assert metrics["evidence_count"] == 2
    assert metrics["artifact_evidence_count"] == 2
    assert metrics["goal_evidence_count"] == 2
    assert metrics["latest_evidence"]["evidence_id"] == "evidence_log"
    assert metrics["evidence_type_summary"]["test"]["total"] == 1


def test_observability_builds_evidence_tree_summary(tmp_path) -> None:
    repository = _seed(tmp_path)

    tree = EngineeringEvidenceObservability(tmp_path, evidence_repository=repository).build_evidence_tree_summary()

    assert tree["ok"] is True
    assert tree["tree"]["programs"][0]["program_id"] == "program_1"
    assert tree["tree"]["programs"][0]["evidence_count"] == 2
    assert tree["tree"]["portfolios"][0]["portfolio_id"] == "portfolio_1"
    assert [item["artifact_id"] for item in tree["tree"]["artifacts"]] == ["artifact_1", "artifact_2"]


def test_evidence_observability_boundary_only_reads_summary() -> None:
    source = OBSERVABILITY_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
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
    assert "summarize_evidence" in source
    assert "create_evidence(" not in source
    assert "delete_evidence(" not in source
