from __future__ import annotations

from core.tasks.engineering_goal_loop import ENGINEERING_GOAL_LOOP_SCHEMA, EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository


class StubRunner:
    def __init__(self, decisions: list[dict]) -> None:
        self.decisions = list(decisions)
        self.calls: list[str] = []

    def run_goal(self, goal_id: str) -> dict:
        self.calls.append(goal_id)
        decision = self.decisions[min(len(self.calls) - 1, len(self.decisions) - 1)]
        adaptive_decision = dict(decision)
        adaptive_decision.setdefault("reason", f"{adaptive_decision['decision']}_reason")
        adaptive_decision.setdefault("continuation_plan", {})
        adaptive_decision.setdefault("root_cause", {})
        return {
            "ok": adaptive_decision["decision"] != "blocked",
            "goal_id": goal_id,
            "runtime_result": {"state": adaptive_decision.get("runtime_state", "running")},
            "runtime_root_cause": adaptive_decision.get("root_cause", {}),
            "adaptive_decision": adaptive_decision,
        }


def _repository(tmp_path) -> EngineeringGoalRepository:
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "goal_1", "summary": "Build demo system"})
    return repository


def _continue_plan(goal_id: str = "goal_1") -> dict:
    return {
        "goal_id": goal_id,
        "reason": "goal_incomplete",
        "remaining_tasks": [f"{goal_id}_result"],
        "next_runtime_request": {
            "goal_id": goal_id,
            "payload": {
                "goal_id": goal_id,
                "task_id": goal_id,
                "package_id": goal_id,
                "goal": "Build demo system",
                "task_type": "engineering_task",
                "remaining_tasks": [f"{goal_id}_result"],
                "continuation_requested": True,
            },
        },
    }


def test_complete_goal_loop_runs_one_cycle_and_stops(tmp_path) -> None:
    runner = StubRunner([{"decision": "complete", "reason": "goal_completed", "runtime_state": "complete"}])

    result = EngineeringGoalLoop(repo_root=tmp_path, repository=_repository(tmp_path), runner=runner).run_until_terminal("goal_1")

    assert result["schema"] == ENGINEERING_GOAL_LOOP_SCHEMA
    assert result["ok"] is True
    assert result["terminal"] is True
    assert result["stop_reason"] == "complete"
    assert result["cycle_count"] == 1
    assert result["cycles"][0]["adaptive_decision"] == "complete"
    assert result["cycles"][0]["continuation_work_item"] == {}
    assert result["execution_path"]["route"] == "Goal -> Adaptive Planner -> Runtime"
    assert result["execution_path"]["goal_id"] == "goal_1"
    assert result["execution_path"]["adaptive_planner_decides_only"] is True
    assert runner.calls == ["goal_1"]


def test_continue_goal_creates_next_continuation_work_item(tmp_path) -> None:
    repository = _repository(tmp_path)
    runner = StubRunner(
        [
            {
                "decision": "continue",
                "reason": "goal_incomplete",
                "runtime_state": "running",
                "continuation_plan": _continue_plan(),
            },
            {"decision": "complete", "reason": "goal_completed", "runtime_state": "complete"},
        ]
    )

    result = EngineeringGoalLoop(repo_root=tmp_path, repository=repository, runner=runner).run_until_terminal("goal_1")

    first_cycle = result["cycles"][0]
    work_item = first_cycle["continuation_work_item"]
    assert result["ok"] is True
    assert result["cycle_count"] == 2
    assert first_cycle["adaptive_decision"] == "continue"
    assert work_item["source_goal_id"] == "goal_1"
    assert work_item["goal_id"] == "goal_1__continuation_1"
    assert repository.load_goal(work_item["goal_id"])["payload"]["continuation_requested"] is True
    assert runner.calls == ["goal_1", "goal_1__continuation_1"]


def test_create_continuation_work_item_can_use_last_cycle(tmp_path) -> None:
    repository = _repository(tmp_path)
    runner = StubRunner(
        [
            {
                "decision": "continue",
                "reason": "goal_incomplete",
                "runtime_state": "running",
                "continuation_plan": _continue_plan(),
            }
        ]
    )
    loop = EngineeringGoalLoop(repo_root=tmp_path, repository=repository, runner=runner)

    cycle = loop.run_one_cycle("goal_1")
    work_item = loop.create_continuation_work_item()

    assert cycle["adaptive_decision"] == "continue"
    assert work_item["goal_id"] == "goal_1__continuation_1"
    assert repository.load_goal(work_item["goal_id"])["metadata"]["source_cycle_index"] == 0


def test_blocked_goal_stops_and_preserves_root_cause(tmp_path) -> None:
    root_cause = {"stop_reason": "verification_failed", "failed_tasks": ["goal_1_result"]}
    runner = StubRunner(
        [
            {
                "decision": "blocked",
                "reason": "verification_failed",
                "runtime_state": "failed",
                "root_cause": root_cause,
            }
        ]
    )

    result = EngineeringGoalLoop(repo_root=tmp_path, repository=_repository(tmp_path), runner=runner).run_until_terminal("goal_1")

    assert result["ok"] is False
    assert result["terminal"] is True
    assert result["stop_reason"] == "blocked"
    assert result["cycle_count"] == 1
    assert result["cycles"][0]["root_cause"] == root_cause


def test_replan_goal_stops_and_creates_replan_record(tmp_path) -> None:
    replan_request = {"goal_id": "goal_1", "reason": "missing_output", "failed_tasks": ["goal_1_result"]}
    runner = StubRunner(
        [
            {
                "decision": "replan",
                "reason": "missing_output",
                "runtime_state": "replan",
                "replan_request": replan_request,
            }
        ]
    )

    result = EngineeringGoalLoop(repo_root=tmp_path, repository=_repository(tmp_path), runner=runner).run_until_terminal("goal_1")

    cycle = result["cycles"][0]
    assert result["ok"] is False
    assert result["terminal"] is True
    assert result["stop_reason"] == "replan"
    assert result["adaptive_decision"]["decision"] == "replan"
    assert cycle["adaptive_decision"] == "replan"
    assert cycle["replan_record"]["reason"] == "missing_output"
    assert cycle["replan_record"]["replan_request"] == replan_request
    assert cycle["continuation_work_item"] == {}


def test_max_cycles_bounds_repeated_continue_decisions(tmp_path) -> None:
    repository = _repository(tmp_path)
    runner = StubRunner(
        [
            {
                "decision": "continue",
                "reason": "goal_incomplete",
                "runtime_state": "running",
                "continuation_plan": _continue_plan(),
            }
        ]
    )

    result = EngineeringGoalLoop(repo_root=tmp_path, repository=repository, runner=runner).run_until_terminal("goal_1", max_cycles=2)

    assert result["ok"] is False
    assert result["terminal"] is False
    assert result["stop_reason"] == "max_cycles_reached"
    assert result["cycle_count"] == 2
    assert [cycle["cycle_index"] for cycle in result["cycles"]] == [0, 1]
    assert len(runner.calls) == 2


def test_goal_loop_does_not_mutate_runner_runtime_or_lifecycle_payloads(tmp_path) -> None:
    runtime_result = {
        "state": "complete",
        "iterations": [
            {
                "continuation_result": {
                    "goal_lifecycle": {
                        "goal_state": "completed",
                        "completed_tasks": ["goal_1_result"],
                    }
                }
            }
        ],
    }
    runner_result = {
        "ok": True,
        "goal_id": "goal_1",
        "runtime_result": runtime_result,
        "goal_lifecycle": runtime_result["iterations"][0]["continuation_result"]["goal_lifecycle"],
        "adaptive_decision": {
            "decision": "complete",
            "reason": "goal_completed",
            "confidence": 0.95,
            "continuation_plan": {},
            "replan_request": {},
            "blocking_issues": [],
        },
    }

    class SingleResultRunner:
        def run_goal(self, goal_id: str) -> dict:
            return runner_result

    before_runtime = {
        "runtime_result": runtime_result.copy(),
        "goal_lifecycle": dict(runner_result["goal_lifecycle"]),
    }

    result = EngineeringGoalLoop(
        repo_root=tmp_path,
        repository=_repository(tmp_path),
        runner=SingleResultRunner(),
    ).run_until_terminal("goal_1")

    assert result["stop_reason"] == "complete"
    assert runner_result["runtime_result"] == before_runtime["runtime_result"]
    assert runner_result["goal_lifecycle"] == before_runtime["goal_lifecycle"]
