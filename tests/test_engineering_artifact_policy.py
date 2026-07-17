from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_artifact_policy import EngineeringArtifactPolicy


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_FILE = REPO_ROOT / "core/tasks/engineering_artifact_policy.py"


def _artifact(artifact_id: str, artifact_type: str, created_at: float, **fields: object) -> dict:
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "artifact_name": artifact_id,
        "created_at": created_at,
        **fields,
    }


def test_classify_artifact_uses_archived_flag_and_lifecycle_state() -> None:
    policy = EngineeringArtifactPolicy()

    assert policy.classify_artifact(_artifact("active", "report", 10)) == "active"
    assert policy.classify_artifact(_artifact("archived_flag", "report", 20, archived=True)) == "archived"
    assert policy.classify_artifact(_artifact("metadata_flag", "report", 30, metadata={"archived": True})) == "archived"
    assert policy.classify_artifact(_artifact("metadata_state", "log", 40, metadata={"artifact_state": "archived"})) == "archived"


def test_active_and_archived_helpers_are_complements() -> None:
    policy = EngineeringArtifactPolicy()
    active = _artifact("active", "report", 10)
    archived = _artifact("archived", "report", 20, archived=True)

    assert policy.is_active_artifact(active) is True
    assert policy.is_archived_artifact(active) is False
    assert policy.is_active_artifact(archived) is False
    assert policy.is_archived_artifact(archived) is True


def test_select_latest_artifact_uses_created_at_then_artifact_id() -> None:
    latest = EngineeringArtifactPolicy().select_latest_artifact(
        [
            _artifact("artifact_a", "report", 10),
            _artifact("artifact_b", "report", 20),
            _artifact("artifact_c", "log", 20),
        ]
    )

    assert latest["artifact_id"] == "artifact_c"


def test_build_artifact_summary_groups_by_archived_flag_and_type() -> None:
    summary = EngineeringArtifactPolicy().build_artifact_summary(
        [
            _artifact("report_1", "report", 10),
            _artifact("report_2", "report", 30, archived=True),
            _artifact("log_1", "log", 20),
        ]
    )

    assert [item["artifact_id"] for item in summary["active"]] == ["report_1", "log_1"]
    assert [item["artifact_id"] for item in summary["archived"]] == ["report_2"]
    assert summary["active_count"] == 2
    assert summary["archived_count"] == 1
    assert summary["latest_artifact"]["artifact_id"] == "report_2"
    assert summary["artifact_type_summary"]["report"]["active"] == 1
    assert summary["artifact_type_summary"]["report"]["archived"] == 1
    assert summary["artifact_type_summary"]["report"]["total"] == 2
    assert summary["artifact_type_summary"]["report"]["latest_artifact"]["artifact_id"] == "report_2"
    assert summary["artifact_type_summary"]["log"]["active"] == 1


def test_artifact_policy_boundary_imports_no_runtime_goal_scheduler_memory_or_ui() -> None:
    tree = ast.parse(POLICY_FILE.read_text(encoding="utf-8"))
    imports: set[str] = set()
    calls: set[str] = set()

    def name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.Call):
            calls.add(name(node.func))

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
    assert imports.isdisjoint(forbidden)
    assert "run_until_terminal" not in calls
    assert "schedule_next_goal" not in calls
