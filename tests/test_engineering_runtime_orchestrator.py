from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_runtime_orchestrator import (
    ENGINEERING_RUNTIME_ORCHESTRATOR_SCHEMA,
    EngineeringRuntimeOrchestrator,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR_FILE = REPO_ROOT / "core/tasks/engineering_runtime_orchestrator.py"


def _goal(goal_id: str, *, status: str = "pending") -> dict:
    return {
        "goal_id": goal_id,
        "priority": 1,
        "status": status,
        "created_at": 1,
        "updated_at": 1,
        "payload": {
            "goal_id": goal_id,
            "task_id": goal_id,
            "package_id": goal_id,
            "goal": f"Goal {goal_id}",
        },
    }


class FakeScheduler:
    def __init__(self, selected_goal_id: str = "goal_1") -> None:
        self.selected_goal_id = selected_goal_id
        self.calls: list[list[dict]] = []

    def schedule_next_goal(self, goals):
        self.calls.append([dict(goal) for goal in goals])
        return {
            "ok": bool(self.selected_goal_id),
            "scheduler_decision": {
                "action": "schedule_next_goal" if self.selected_goal_id else "no_runnable_goal",
                "selected_goal_id": self.selected_goal_id,
                "reason": "selected" if self.selected_goal_id else "no_runnable_goals_available",
                "skipped_goals": [],
                "deferred_goals": [],
            },
            "execution_path": {"direct_execution": False, "new_execution_path": False},
        }


class FakeDependencyGraph:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.calls: list[tuple[str, dict]] = []

    def prerequisite_status(self, goal_id, goal_statuses):
        self.calls.append((goal_id, dict(goal_statuses)))
        return {
            "goal_id": goal_id,
            "ready": self.ready,
            "complete": self.ready,
            "missing_prerequisites": [] if self.ready else ["setup"],
            "blocked_by_goals": [],
            "reason": "dependencies_satisfied" if self.ready else "dependencies_unsatisfied",
        }

    def as_dict(self, goal_statuses=None):
        return {
            "records": [],
            "dependency_status": {
                "ok": self.ready,
                "completion": [],
                "blocked_goals": [],
                "goal_statuses": dict(goal_statuses or {}),
            },
        }


class FakePlanningLoop:
    def __init__(self, goal_state: str = "running") -> None:
        self.goal_state = goal_state
        self.calls: list[dict] = []

    def run(self, payload):
        self.calls.append(dict(payload))
        return {
            "ok": self.goal_state == "completed",
            "goal_id": payload["goal_id"],
            "goal_state": self.goal_state,
            "goal_lifecycle": {
                "goal_id": payload["goal_id"],
                "goal_state": self.goal_state,
                "task_buckets": {"pending": [], "running": [], "completed": [], "blocked": []},
            },
            "task_buckets": {"pending": [], "running": [], "completed": [], "blocked": []},
            "memory": {"records": []},
        }


class FakeContinuationCoordinator:
    def __init__(self, goal_state: str = "running") -> None:
        self.goal_state = goal_state
        self.calls: list[dict] = []

    def continue_goal(self, payload):
        self.calls.append(dict(payload))
        return {
            "ok": self.goal_state == "completed",
            "terminal": self.goal_state in {"completed", "blocked", "cancelled"},
            "stopped_reason": self.goal_state,
            "goal_lifecycle": {
                "goal_id": payload["goal_id"],
                "goal_state": self.goal_state,
                "task_buckets": {"pending": [], "running": [], "completed": [], "blocked": []},
            },
        }


class FakeEvaluator:
    def __init__(self, decision: str) -> None:
        self.decision = decision
        self.calls: list[dict] = []

    def evaluate(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {
            "decision": self.decision,
            "reason": f"fake_{self.decision}",
            "terminal": self.decision in {"block", "complete"},
            "replan_requested": self.decision == "replan",
        }


class FakeLifecycleApplier:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def apply_evaluator_decision(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {
            "ok": True,
            "delegated": True,
            "decision": dict(kwargs["evaluator_decision"]),
        }


def _orchestrator(
    tmp_path,
    *,
    scheduler=None,
    dependency_graph=None,
    planning_loop=None,
    evaluator=None,
    continuation=None,
    lifecycle=None,
    max_iterations: int = 2,
) -> EngineeringRuntimeOrchestrator:
    return EngineeringRuntimeOrchestrator(
        repo_root=tmp_path,
        scheduler=scheduler or FakeScheduler(),
        dependency_graph=dependency_graph or FakeDependencyGraph(),
        planning_loop=planning_loop or FakePlanningLoop(),
        evaluator=evaluator or FakeEvaluator("continue"),
        continuation_coordinator=continuation or FakeContinuationCoordinator(),
        lifecycle_decision_applier=lifecycle or FakeLifecycleApplier(),
        max_iterations=max_iterations,
    )


def test_runtime_orchestrator_runs_runnable_goal(tmp_path) -> None:
    scheduler = FakeScheduler("goal_1")
    dependency_graph = FakeDependencyGraph(ready=True)
    planning = FakePlanningLoop("running")
    continuation = FakeContinuationCoordinator("running")
    evaluator = FakeEvaluator("continue")
    lifecycle = FakeLifecycleApplier()

    result = _orchestrator(
        tmp_path,
        scheduler=scheduler,
        dependency_graph=dependency_graph,
        planning_loop=planning,
        continuation=continuation,
        evaluator=evaluator,
        lifecycle=lifecycle,
        max_iterations=1,
    ).run([_goal("goal_1")])

    assert result["schema"] == ENGINEERING_RUNTIME_ORCHESTRATOR_SCHEMA
    assert result["state"] == "running"
    assert scheduler.calls
    assert dependency_graph.calls == [("goal_1", {"goal_1": "pending"})]
    assert planning.calls[0]["engineering_goal_lifecycle"] is True
    assert continuation.calls[0]["goal_id"] == "goal_1"
    assert evaluator.calls[0]["current_goal_state"]["goal_state"] == "running"
    assert lifecycle.calls[0]["evaluator_decision"]["decision"] == "continue"
    assert result["execution_path"]["direct_execution"] is False


def test_runtime_orchestrator_blocks_on_dependency(tmp_path) -> None:
    planning = FakePlanningLoop()
    continuation = FakeContinuationCoordinator()
    evaluator = FakeEvaluator("continue")

    result = _orchestrator(
        tmp_path,
        dependency_graph=FakeDependencyGraph(ready=False),
        planning_loop=planning,
        continuation=continuation,
        evaluator=evaluator,
    ).run([_goal("goal_1")])

    assert result["state"] == "blocked"
    assert result["stop_reason"] == "dependencies_unsatisfied"
    assert planning.calls == []
    assert continuation.calls == []
    assert evaluator.calls == []
    assert result["runtime_trace"][-1]["event"] == "dependencies_validated"


def test_runtime_orchestrator_replans_when_evaluator_requests_replan(tmp_path) -> None:
    scheduler = FakeScheduler("goal_1")
    evaluator = FakeEvaluator("replan")

    result = _orchestrator(
        tmp_path,
        scheduler=scheduler,
        evaluator=evaluator,
        max_iterations=2,
    ).run([_goal("goal_1")])

    assert result["state"] == "replan"
    assert result["stop_reason"] == "evaluator_requested_replan"
    assert len(result["iterations"]) == 2
    assert [item["state"] for item in result["iterations"]] == ["replan", "replan"]


def test_runtime_orchestrator_completes_goal(tmp_path) -> None:
    result = _orchestrator(
        tmp_path,
        planning_loop=FakePlanningLoop("completed"),
        continuation=FakeContinuationCoordinator("completed"),
        evaluator=FakeEvaluator("complete"),
    ).run([_goal("goal_1")])

    assert result["ok"] is True
    assert result["state"] == "complete"
    assert result["terminal"] is True
    assert result["iterations"][0]["lifecycle_result"]["delegated"] is True


def test_runtime_orchestrator_idles_with_no_runnable_goals(tmp_path) -> None:
    planning = FakePlanningLoop()
    continuation = FakeContinuationCoordinator()
    evaluator = FakeEvaluator("continue")

    result = _orchestrator(
        tmp_path,
        scheduler=FakeScheduler(""),
        planning_loop=planning,
        continuation=continuation,
        evaluator=evaluator,
    ).run([_goal("goal_1", status="completed")])

    assert result["state"] == "idle"
    assert result["stop_reason"] == "no_runnable_goals"
    assert planning.calls == []
    assert continuation.calls == []
    assert evaluator.calls == []


def test_runtime_orchestrator_owns_orchestration_only() -> None:
    tree = ast.parse(ORCHESTRATOR_FILE.read_text(encoding="utf-8"))
    imports = set()
    calls = set()

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
                imports.add(alias.asname or alias.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
            for alias in node.names:
                imports.add(alias.name)
                imports.add(alias.asname or alias.name)
        elif isinstance(node, ast.Call):
            calls.add(name(node.func))

    forbidden_imports = {
        "EngineeringTaskRunner",
        "core.tasks.engineering_task_runner",
        "run_engineering_task",
        "EngineeringMemoryStore",
        "core.tasks.engineering_memory_store",
        "Planner",
        "core.planning.planner",
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
    assert not any(call.endswith(".submit") for call in calls)
