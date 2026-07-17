from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_evidence_policy import EngineeringEvidencePolicy


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_FILE = REPO_ROOT / "core/tasks/engineering_evidence_policy.py"


def _evidence(evidence_id: str, evidence_type: str, created_at: float, **fields: object) -> dict:
    return {
        "evidence_id": evidence_id,
        "evidence_type": evidence_type,
        "evidence_name": evidence_id,
        "created_at": created_at,
        **fields,
    }


def test_policy_classifies_evidence_by_archived_flag_and_state() -> None:
    policy = EngineeringEvidencePolicy()

    assert policy.classify_evidence(_evidence("active", "test", 10)) == "active"
    assert policy.classify_evidence(_evidence("flag", "test", 20, archived=True)) == "archived"
    assert policy.classify_evidence(_evidence("metadata_flag", "test", 30, metadata={"archived": True})) == "archived"
    assert policy.classify_evidence(_evidence("metadata_state", "log", 40, metadata={"evidence_state": "archived"})) == "archived"


def test_active_and_archived_helpers_are_complements() -> None:
    policy = EngineeringEvidencePolicy()
    active = _evidence("active", "test", 10)
    archived = _evidence("archived", "test", 20, archived=True)

    assert policy.is_active_evidence(active) is True
    assert policy.is_archived_evidence(active) is False
    assert policy.is_active_evidence(archived) is False
    assert policy.is_archived_evidence(archived) is True


def test_select_latest_evidence_uses_created_at_then_evidence_id() -> None:
    latest = EngineeringEvidencePolicy().select_latest_evidence(
        [
            _evidence("evidence_a", "test", 10),
            _evidence("evidence_b", "test", 20),
            _evidence("evidence_c", "log", 20),
        ]
    )

    assert latest["evidence_id"] == "evidence_c"


def test_build_evidence_summary_groups_by_archived_flag_and_type() -> None:
    summary = EngineeringEvidencePolicy().build_evidence_summary(
        [
            _evidence("test_1", "test", 10),
            _evidence("test_2", "test", 30, archived=True),
            _evidence("log_1", "log", 20),
        ]
    )

    assert [item["evidence_id"] for item in summary["active"]] == ["test_1", "log_1"]
    assert [item["evidence_id"] for item in summary["archived"]] == ["test_2"]
    assert summary["active_count"] == 2
    assert summary["archived_count"] == 1
    assert summary["latest_evidence"]["evidence_id"] == "test_2"
    assert summary["evidence_type_summary"]["test"]["active"] == 1
    assert summary["evidence_type_summary"]["test"]["archived"] == 1
    assert summary["evidence_type_summary"]["test"]["total"] == 2
    assert summary["evidence_type_summary"]["test"]["latest_evidence"]["evidence_id"] == "test_2"
    assert summary["evidence_type_summary"]["log"]["active"] == 1


def test_evidence_policy_boundary_imports_no_runtime_goal_scheduler_memory_or_ui() -> None:
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
