from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_adaptive_planner import (
    ENGINEERING_ADAPTIVE_DECISION_SCHEMA,
    ENGINEERING_CONTINUATION_PLAN_SCHEMA,
    EngineeringAdaptivePlanner,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PLANNER_FILE = REPO_ROOT / "core/tasks/engineering_adaptive_planner.py"


def _goal() -> dict:
    return {
        "goal_id": "goal_1",
        "summary": "Build demo system",
        "payload": {
            "goal_id": "goal_1",
            "task_id": "goal_1",
            "package_id": "goal_1",
            "goal": "Build demo system",
            "task_type": "engineering_task",
        },
    }


def _runtime(*, ok: bool, state: str, goal_state: str, remaining=None, completed=None, failed=None, blocked=None) -> dict:
    return {
        "ok": ok,
        "state": state,
        "decision_state": state,
        "iterations": [
            {
                "goal_id": "goal_1",
                "state": state,
                "continuation_result": {
                    "ok": ok,
                    "terminal": goal_state in {"completed", "blocked", "failed", "cancelled"},
                    "stopped_reason": goal_state,
                    "goal_lifecycle": {
                        "goal_id": "goal_1",
                        "goal_state": goal_state,
                        "completed_tasks": list(completed or []),
                        "remaining_tasks": list(remaining or []),
                        "failed_tasks": list(failed or []),
                        "blocked_tasks": list(blocked or []),
                    },
                },
            }
        ],
    }


def test_adaptive_planner_marks_completed_goal_complete() -> None:
    decision = EngineeringAdaptivePlanner().decide_next_action(
        goal=_goal(),
        runtime_result=_runtime(ok=True, state="complete", goal_state="completed", completed=["a", "b"]),
    )

    assert decision["schema"] == ENGINEERING_ADAPTIVE_DECISION_SCHEMA
    assert decision["decision"] == "complete"
    assert decision["terminal"] is True
    assert decision["continuation_plan"] == {}
    assert decision["progress"]["complete"] is True


def test_adaptive_planner_continues_incomplete_goal_with_plan() -> None:
    decision = EngineeringAdaptivePlanner().decide_next_action(
        goal=_goal(),
        runtime_result=_runtime(
            ok=True,
            state="running",
            goal_state="next_task_generated",
            completed=["goal_1_breakdown"],
            remaining=["goal_1_result"],
        ),
    )

    plan = decision["continuation_plan"]
    assert decision["decision"] == "continue"
    assert decision["terminal"] is False
    assert plan["schema"] == ENGINEERING_CONTINUATION_PLAN_SCHEMA
    assert plan["remaining_tasks"] == ["goal_1_result"]
    assert plan["next_runtime_request"]["payload"]["continuation_requested"] is True
    assert plan["execution_path"]["executes_tasks"] is False


def test_adaptive_planner_blocks_runtime_failure_with_root_cause() -> None:
    root_cause = {"stop_reason": "verification_failed", "failed_tasks": ["goal_1_result"]}
    decision = EngineeringAdaptivePlanner().decide_next_action(
        goal=_goal(),
        runtime_result=_runtime(
            ok=False,
            state="failed",
            goal_state="failed",
            completed=["goal_1_breakdown"],
            failed=["goal_1_result"],
        ),
        runtime_root_cause=root_cause,
    )

    assert decision["decision"] == "blocked"
    assert decision["terminal"] is True
    assert decision["root_cause"] == root_cause
    assert decision["progress"]["failed_tasks"] == ["goal_1_result"]
    assert decision["continuation_plan"] == {}


def test_adaptive_planner_does_not_import_execution_or_repository_owners() -> None:
    tree = ast.parse(PLANNER_FILE.read_text(encoding="utf-8"))
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
        "EngineeringGoalRepository",
        "EngineeringRuntimeOrchestrator",
        "EngineeringTaskRunner",
        "run_engineering_task",
        "WorkPackageScheduler",
        "core.tasks.engineering_task_runner",
        "core.tasks.engineering_runtime_orchestrator",
        "core.tasks.engineering_goal_repository",
    }
    assert imports.isdisjoint(forbidden)
    assert "run_engineering_task" not in calls
    assert "submit_work_package" not in calls
    assert not any(call.endswith(".submit") for call in calls)
