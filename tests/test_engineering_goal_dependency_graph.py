from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_goal_dependency_graph import (
    EngineeringGoalDependencyGraph,
    EngineeringGoalDependencyRecord,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPENDENCY_GRAPH_FILE = REPO_ROOT / "core/tasks/engineering_goal_dependency_graph.py"


def _imports() -> set[str]:
    tree = ast.parse(DEPENDENCY_GRAPH_FILE.read_text(encoding="utf-8"))
    symbols: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                symbols.add(alias.name)
                symbols.add(alias.asname or alias.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            symbols.add(module)
            for alias in node.names:
                symbols.add(alias.name)
                symbols.add(alias.asname or alias.name)
                symbols.add(f"{module}.{alias.name}")
    return symbols


def _calls() -> set[str]:
    tree = ast.parse(DEPENDENCY_GRAPH_FILE.read_text(encoding="utf-8"))

    def name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

    return {name(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}


def test_dependency_registration() -> None:
    graph = EngineeringGoalDependencyGraph()

    result = graph.register(
        {
            "goal_id": "child",
            "parent_goal_ids": ["parent"],
            "prerequisite_goal_ids": ["parent"],
        }
    )

    assert result["ok"] is True
    assert result["goal_id"] == "child"
    assert result["dependency_record"]["goal_id"] == "child"
    assert graph.as_dict()["records"][0]["goal_id"] == "child"


def test_parent_child_relationship() -> None:
    graph = EngineeringGoalDependencyGraph(
        [
            {"goal_id": "parent", "child_goal_ids": ["child"]},
            {"goal_id": "child", "parent_goal_ids": ["parent"]},
        ]
    )

    assert graph.parent_child_relationships() == [
        {"parent_goal_id": "parent", "child_goal_id": "child"},
    ]
    assert graph.validate()["ok"] is True


def test_prerequisite_validation() -> None:
    graph = EngineeringGoalDependencyGraph(
        [
            {"goal_id": "build"},
            {"goal_id": "deploy", "prerequisite_goal_ids": ["build"]},
        ]
    )

    blocked = graph.prerequisite_status("deploy", {"build": "running", "deploy": "pending"})
    ready = graph.prerequisite_status("deploy", {"build": "completed", "deploy": "pending"})

    assert blocked["ready"] is False
    assert blocked["missing_prerequisites"] == ["build"]
    assert ready["ready"] is True
    assert ready["missing_prerequisites"] == []


def test_blocked_dependency_detection() -> None:
    graph = EngineeringGoalDependencyGraph(
        [
            {"goal_id": "security_review"},
            {"goal_id": "release", "blocked_by_goal_ids": ["security_review"]},
        ]
    )

    blocked = graph.blocked_goals({"security_review": "blocked", "release": "pending"})

    assert blocked == [
        {
            "goal_id": "release",
            "missing_prerequisites": [],
            "blocked_by_goals": ["security_review"],
            "blocking_status_goals": ["security_review"],
        }
    ]


def test_dependency_completion_evaluation() -> None:
    graph = EngineeringGoalDependencyGraph(
        [
            {"goal_id": "build"},
            EngineeringGoalDependencyRecord(goal_id="test", prerequisite_goal_ids=["build"]),
            {"goal_id": "ship", "prerequisite_goal_ids": ["build", "test"]},
        ]
    )

    completion = graph.completion_status({"build": "completed", "test": "running", "ship": "pending"})

    assert completion == [
        {
            "goal_id": "build",
            "dependencies_complete": True,
            "status": "completed",
            "missing_prerequisites": [],
            "blocked_by_goals": [],
        },
        {
            "goal_id": "ship",
            "dependencies_complete": False,
            "status": "pending",
            "missing_prerequisites": ["test"],
            "blocked_by_goals": [],
        },
        {
            "goal_id": "test",
            "dependencies_complete": True,
            "status": "running",
            "missing_prerequisites": [],
            "blocked_by_goals": [],
        },
    ]


def test_cycle_detection() -> None:
    graph = EngineeringGoalDependencyGraph(
        [
            {"goal_id": "a", "prerequisite_goal_ids": ["c"]},
            {"goal_id": "b", "prerequisite_goal_ids": ["a"]},
            {"goal_id": "c", "prerequisite_goal_ids": ["b"]},
        ]
    )

    assert graph.detect_cycles() == [["a", "c", "b", "a"]]
    validation = graph.validate()
    assert validation["ok"] is False
    assert validation["errors"][0]["reason"] == "dependency_cycle"


def test_deterministic_dependency_graph_output() -> None:
    records = [
        {"goal_id": "z", "prerequisite_goal_ids": ["a"], "child_goal_ids": ["zz"]},
        {"goal_id": "a"},
        {"goal_id": "zz", "parent_goal_ids": ["z"]},
    ]
    graph = EngineeringGoalDependencyGraph(records)
    reversed_graph = EngineeringGoalDependencyGraph(list(reversed(records)))

    assert graph.as_dict({"a": "completed", "z": "pending", "zz": "pending"}) == reversed_graph.as_dict(
        {"zz": "pending", "z": "pending", "a": "completed"}
    )
    assert [record["goal_id"] for record in graph.as_dict()["records"]] == ["a", "z", "zz"]


def test_dependency_graph_does_not_execute_schedule_plan_or_persist() -> None:
    imports = _imports()
    calls = _calls()

    forbidden_imports = {
        "EngineeringGoalScheduler",
        "core.tasks.engineering_goal_scheduler",
        "EngineeringGoalPortfolio",
        "core.tasks.engineering_goal_portfolio",
        "Planner",
        "core.planning.planner",
        "EngineeringPlanningLoop",
        "core.tasks.engineering_planning_loop",
        "EngineeringTaskRunner",
        "core.tasks.engineering_task_runner",
        "run_engineering_task",
        "EngineeringMemoryStore",
        "core.tasks.engineering_memory_store",
        "EngineeringGoalLifecycle",
        "core.tasks.engineering_goal_lifecycle",
        "WorkPackageScheduler",
        "core.tasks.work_package_scheduler",
        "AgentLoop",
        "core.agent.agent_loop",
    }
    assert imports.isdisjoint(forbidden_imports)
    assert "run_engineering_task" not in calls
    assert "submit_work_package" not in calls
    assert "save_record" not in calls
    assert "load_relevant_memory" not in calls
    assert not any(call.endswith(".plan") for call in calls)
