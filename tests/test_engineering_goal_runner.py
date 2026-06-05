from __future__ import annotations

from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_goal_runner import (
    ENGINEERING_GOAL_RUNNER_SCHEMA,
    ENGINEERING_GOAL_RUNTIME_REQUEST_SCHEMA,
    EngineeringGoalRunner,
)
from core.tasks.engineering_planning_adapter import EngineeringPlanningOnlyAdapter


class SpyRuntimeOrchestrator:
    def __init__(self, *, ok: bool = True, state: str = "running") -> None:
        self.calls: list[list[dict]] = []
        self.ok = ok
        self.state = state

    def run(self, goals):
        records = [dict(goal) for goal in goals]
        self.calls.append(records)
        goal_id = records[0]["goal_id"] if records else ""
        return {
            "ok": self.ok,
            "schema": "zero.engineering_runtime_orchestrator.v1",
            "state": self.state,
            "decision_state": self.state,
            "stop_reason": self.state,
            "iterations": [{"goal_id": goal_id, "state": self.state}] if goal_id else [],
            "execution_path": {"direct_execution": False},
        }


def test_run_goal_loads_goal_and_invokes_runtime_orchestrator(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    goal = repository.save_goal({"goal_id": "goal_1", "summary": "Build demo system"})
    orchestrator = SpyRuntimeOrchestrator()

    result = EngineeringGoalRunner(
        repo_root=tmp_path,
        repository=repository,
        runtime_orchestrator=orchestrator,
    ).run_goal("goal_1")

    assert result["schema"] == ENGINEERING_GOAL_RUNNER_SCHEMA
    assert result["ok"] is True
    assert result["action"] == "run_goal"
    assert result["goal_id"] == "goal_1"
    assert orchestrator.calls == [[result["runtime_request"]["goals"][0]]]
    assert orchestrator.calls[0][0]["goal_id"] == goal["goal_id"]
    assert orchestrator.calls[0][0]["payload"]["goal"] == "Build demo system"
    assert result["runtime_result"]["schema"] == "zero.engineering_runtime_orchestrator.v1"
    assert result["execution_path"]["goal_runner_bridges_only"] is True
    assert result["execution_path"]["goal_repository_in_orchestrator"] is False


def test_run_next_goal_passes_repository_goals_to_runtime(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "low", "summary": "Low", "priority": 1})
    repository.save_goal({"goal_id": "high", "summary": "High", "priority": 10})
    orchestrator = SpyRuntimeOrchestrator()

    result = EngineeringGoalRunner(
        repo_root=tmp_path,
        repository=repository,
        runtime_orchestrator=orchestrator,
    ).run_next_goal()

    assert result["ok"] is True
    assert result["action"] == "run_next_goal"
    assert [goal["goal_id"] for goal in orchestrator.calls[0]] == ["high", "low"]
    assert result["runtime_request"]["selected_goal_id"] == ""
    assert result["runtime_request"]["execution_path"]["runtime_orchestrator_owns_runtime_loop"] is True


def test_build_runtime_request_normalizes_goal_payload(tmp_path) -> None:
    request = EngineeringGoalRunner(
        repo_root=tmp_path,
        repository=EngineeringGoalRepository(tmp_path),
        runtime_orchestrator=SpyRuntimeOrchestrator(),
    ).build_runtime_request(
        [{"goal_id": "goal_1", "summary": "Normalize me"}],
        selected_goal_id="goal_1",
    )

    assert request["schema"] == ENGINEERING_GOAL_RUNTIME_REQUEST_SCHEMA
    assert request["selected_goal_id"] == "goal_1"
    assert request["goals"][0]["payload"]["task_type"] == "engineering_task"
    assert request["goals"][0]["payload"]["package_id"] == "goal_1"
    assert request["execution_path"]["repository_persists_only"] is True
    assert request["execution_path"]["goal_runner_bridges_only"] is True


def test_run_goal_returns_not_found_without_invoking_runtime(tmp_path) -> None:
    orchestrator = SpyRuntimeOrchestrator()

    result = EngineeringGoalRunner(
        repo_root=tmp_path,
        repository=EngineeringGoalRepository(tmp_path),
        runtime_orchestrator=orchestrator,
    ).run_goal("missing")

    assert result["ok"] is False
    assert result["error"] == "engineering_goal_not_found"
    assert orchestrator.calls == []


def test_run_goal_reports_runtime_failure_without_hiding_it(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "goal_1", "summary": "Build demo system"})
    orchestrator = SpyRuntimeOrchestrator(ok=False, state="replan")

    result = EngineeringGoalRunner(
        repo_root=tmp_path,
        repository=repository,
        runtime_orchestrator=orchestrator,
    ).run_goal("goal_1")

    assert result["ok"] is False
    assert result["runtime_result"]["state"] == "replan"
    assert result["runtime_root_cause"]["state"] == "replan"


def test_goal_runner_uses_named_planning_only_boundary() -> None:
    import core.tasks.engineering_goal_runner as runner_module

    assert runner_module.EngineeringPlanningOnlyAdapter is EngineeringPlanningOnlyAdapter
    assert not hasattr(runner_module, "_PlanningOnlyLoop")
    assert not hasattr(runner_module, "_NoMemoryStore")
