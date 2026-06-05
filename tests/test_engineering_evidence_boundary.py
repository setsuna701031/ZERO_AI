from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_FILES = [
    REPO_ROOT / "core/tasks/engineering_evidence_repository.py",
    REPO_ROOT / "core/tasks/engineering_evidence_state.py",
    REPO_ROOT / "core/tasks/engineering_evidence_policy.py",
    REPO_ROOT / "core/tasks/engineering_evidence_observability.py",
    REPO_ROOT / "cli/evidence_cli.py",
]


def test_evidence_layer_boundary_scan_has_no_runtime_scheduler_aer_memory_or_ui() -> None:
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

    for path in EVIDENCE_FILES:
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
        assert imports.isdisjoint(forbidden), path


def test_evidence_layer_does_not_import_or_modify_artifact_repository_schema() -> None:
    for path in EVIDENCE_FILES:
        source = path.read_text(encoding="utf-8")
        assert "EngineeringArtifactRepository" not in source
        assert "engineering_artifact_repository" not in source
        assert "ENGINEERING_ARTIFACT_RECORD_SCHEMA" not in source
