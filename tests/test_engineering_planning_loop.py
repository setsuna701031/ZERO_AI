from __future__ import annotations

import copy
from pathlib import Path

from core.tasks.engineering_planning_loop import EngineeringPlanningLoop


def _write_step(package_id: str, target_path: str, content: str) -> dict:
    return {
        "package_id": package_id,
        "goal": f"Write {target_path}",
        "edits": [
            {
                "operation": "write_file",
                "target_path": target_path,
                "content": content,
                "verify_contains": content.strip(),
            }
        ],
    }


def _payload(goal_id: str) -> dict:
    return {
        "task_type": "engineering_task",
        "goal_id": goal_id,
        "task_id": goal_id,
        "package_id": goal_id,
        "goal": f"Planning loop goal {goal_id}",
        "mode": "execute",
        "approval": True,
    }


class FakePlanner:
    def __init__(self, plans: list[list[dict]]) -> None:
        self.plans = [copy.deepcopy(plan) for plan in plans]
        self.calls: list[dict] = []

    def plan(self, *, context=None, user_input="", route=None, **_kwargs):
        self.calls.append({"context": copy.deepcopy(context or {}), "user_input": user_input, "route": copy.deepcopy(route or {})})
        index = min(len(self.calls) - 1, len(self.plans) - 1)
        steps = copy.deepcopy(self.plans[index])
        return {
            "schema": "fake.planner.result.v1",
            "planner_mode": "fake_engineering_planner",
            "task_buckets": {
                "pending": [
                    {
                        "summary": {
                            "task_id": step["package_id"],
                            "goal": step["goal"],
                            "step_index": offset,
                        },
                        "task_payload": step,
                    }
                    for offset, step in enumerate(steps, start=1)
                ]
            },
            "steps": steps,
        }


class SpyCoordinator:
    def __init__(self, lifecycles: list[dict]) -> None:
        self.lifecycles = [copy.deepcopy(item) for item in lifecycles]
        self.calls: list[dict] = []

    def continue_goal(self, payload):
        self.calls.append(copy.deepcopy(dict(payload)))
        lifecycle = copy.deepcopy(self.lifecycles[min(len(self.calls) - 1, len(self.lifecycles) - 1)])
        return {
            "schema": "zero.engineering_goal.continuation.v1",
            "ok": lifecycle.get("goal_state") == "completed",
            "mode": "goal_continuation_coordinator",
            "terminal": lifecycle.get("goal_state") in {"completed", "blocked", "failed", "cancelled"},
            "goal_lifecycle": lifecycle,
            "latest_result": {
                "result_bundle": {
                    "execution_path": {
                        "no_new_runtime_path": True,
                        "direct_write_shortcut": False,
                    }
                }
            },
            "execution_path": {
                "orchestrates_only": True,
                "sequence": "GoalLifecycle -> EngineeringTaskRunner -> GoalLifecycle",
                "existing_aer_path_reused": True,
                "new_execution_path": False,
            },
        }


class SpyEvaluator:
    def __init__(self, decisions: list[dict]) -> None:
        self.decisions = [copy.deepcopy(item) for item in decisions]
        self.calls: list[dict] = []

    def evaluate(
        self,
        *,
        latest_execution_result,
        current_goal_state,
        current_task_buckets,
        memory_summary=None,
    ):
        self.calls.append(
            {
                "latest_execution_result": copy.deepcopy(latest_execution_result),
                "current_goal_state": copy.deepcopy(current_goal_state),
                "current_task_buckets": copy.deepcopy(current_task_buckets),
                "memory_summary": copy.deepcopy(memory_summary or {}),
            }
        )
        index = min(len(self.calls) - 1, len(self.decisions) - 1)
        return copy.deepcopy(self.decisions[index])


def test_goal_plan_task_buckets(tmp_path: Path) -> None:
    step = _write_step("planning_loop_bucket_task", "workspace/planning_loop_bucket.txt", "bucket\n")
    planner = FakePlanner([[step]])

    result = EngineeringPlanningLoop(repo_root=tmp_path, planner=planner).run(_payload("planning_loop_bucket"))

    lifecycle = result["goal_lifecycle"]
    assert result["ok"] is True
    assert planner.calls
    assert result["planning_events"][0]["planner_called"] is True
    assert result["planning_events"][0]["task_buckets"]["pending"][0]["summary"]["task_id"] == "planning_loop_bucket_task"
    assert lifecycle["task_buckets"]["completed"][0]["summary"]["task_id"] == "planning_loop_bucket_task"
    assert Path(lifecycle["state_path"]).exists()
    assert (tmp_path / "workspace/planning_loop_bucket.txt").read_text(encoding="utf-8") == "bucket\n"


def test_planning_loop_does_not_execute_directly(tmp_path: Path) -> None:
    step = _write_step("planning_loop_delegate_task", "workspace/planning_loop_delegate.txt", "delegate\n")
    lifecycle = {
        "goal_id": "planning_loop_delegate",
        "goal_state": "completed",
        "completed_tasks": ["planning_loop_delegate_task"],
        "remaining_tasks": [],
        "task_buckets": {"pending": [], "running": [], "completed": [], "blocked": [], "failed": [], "cancelled": []},
    }
    coordinator = SpyCoordinator([lifecycle])

    result = EngineeringPlanningLoop(
        repo_root=tmp_path,
        planner=FakePlanner([[step]]),
        continuation_coordinator=coordinator,
    ).run(_payload("planning_loop_delegate"))

    assert len(coordinator.calls) == 1
    assert coordinator.calls[0]["steps"][0]["package_id"] == "planning_loop_delegate_task"
    assert result["execution_path"]["direct_execution"] is False
    assert result["execution_path"]["continuation_coordinator_executes"] is True
    assert not (tmp_path / "workspace/planning_loop_delegate.txt").exists()


def test_continuation_coordinator_remains_execution_orchestrator(tmp_path: Path) -> None:
    step = _write_step("planning_loop_orchestrator_task", "workspace/planning_loop_orchestrator.txt", "orchestrated\n")

    result = EngineeringPlanningLoop(repo_root=tmp_path, planner=FakePlanner([[step]])).run(_payload("planning_loop_orchestrator"))

    continuation_path = result["continuation_result"]["execution_path"]
    nested_path = result["continuation_result"]["latest_result"]["result_bundle"]["step_results"][0]["result"]["result_bundle"]["execution_path"]
    assert continuation_path["sequence"] == "GoalLifecycle -> EngineeringTaskRunner -> GoalLifecycle"
    assert continuation_path["existing_aer_path_reused"] is True
    assert nested_path["no_new_runtime_path"] is True
    assert nested_path["direct_write_shortcut"] is False


def test_replan_after_blocked_task(tmp_path: Path) -> None:
    blocked = _write_step("planning_loop_blocked_task", "core/runtime/planning_loop_blocked.py", "blocked\n")
    replanned = _write_step("planning_loop_replanned_task", "workspace/planning_loop_replanned.txt", "replanned\n")

    result = EngineeringPlanningLoop(
        repo_root=tmp_path,
        planner=FakePlanner([[blocked], [replanned]]),
        max_replans=1,
    ).run(_payload("planning_loop_blocked"))

    lifecycle = result["goal_lifecycle"]
    assert result["ok"] is True
    assert result["replan_count"] == 1
    assert result["replans"][0]["reason"] == "blocked_task"
    assert lifecycle["goal_state"] == "completed"
    assert lifecycle["superseded_tasks"] == ["planning_loop_blocked_task"]
    assert lifecycle["completed_tasks"] == ["planning_loop_replanned_task"]
    assert not (tmp_path / "core/runtime/planning_loop_blocked.py").exists()
    assert (tmp_path / "workspace/planning_loop_replanned.txt").read_text(encoding="utf-8") == "replanned\n"


def test_replan_after_incomplete_goal(tmp_path: Path) -> None:
    initial = _write_step("planning_loop_incomplete_initial", "workspace/planning_loop_incomplete_initial.txt", "initial\n")
    follow_up = _write_step("planning_loop_incomplete_follow_up", "workspace/planning_loop_incomplete_follow_up.txt", "follow up\n")
    incomplete_lifecycle = {
        "goal_id": "planning_loop_incomplete",
        "goal_state": "next_task_generated",
        "completed_tasks": ["planning_loop_incomplete_initial"],
        "remaining_tasks": [],
        "blocked_tasks": [],
        "failed_tasks": [],
        "task_buckets": {"pending": [], "running": [], "completed": [], "blocked": [], "failed": [], "cancelled": []},
    }
    completed_lifecycle = {
        "goal_id": "planning_loop_incomplete",
        "goal_state": "completed",
        "completed_tasks": ["planning_loop_incomplete_initial", "planning_loop_incomplete_follow_up"],
        "remaining_tasks": [],
        "blocked_tasks": [],
        "failed_tasks": [],
        "task_buckets": {"pending": [], "running": [], "completed": [], "blocked": [], "failed": [], "cancelled": []},
    }
    coordinator = SpyCoordinator([incomplete_lifecycle, completed_lifecycle])

    result = EngineeringPlanningLoop(
        repo_root=tmp_path,
        planner=FakePlanner([[initial], [follow_up]]),
        continuation_coordinator=coordinator,
        max_replans=1,
    ).run(_payload("planning_loop_incomplete"))

    assert result["ok"] is True
    assert result["replan_count"] == 1
    assert result["replans"][0]["reason"] == "tasks_exhausted_goal_incomplete"
    assert len(coordinator.calls) == 2
    assert coordinator.calls[1]["steps"][-1]["package_id"] == "planning_loop_incomplete_follow_up"


def test_planning_loop_uses_evaluator_before_replan(tmp_path: Path) -> None:
    initial = _write_step("planning_loop_eval_initial", "workspace/planning_loop_eval_initial.txt", "initial\n")
    follow_up = _write_step("planning_loop_eval_follow_up", "workspace/planning_loop_eval_follow_up.txt", "follow\n")
    incomplete_lifecycle = {
        "goal_id": "planning_loop_eval",
        "goal_state": "next_task_generated",
        "completed_tasks": ["planning_loop_eval_initial"],
        "remaining_tasks": [],
        "blocked_tasks": [],
        "failed_tasks": [],
        "task_buckets": {"pending": [], "running": [], "completed": [], "blocked": [], "failed": [], "cancelled": []},
    }
    completed_lifecycle = {
        "goal_id": "planning_loop_eval",
        "goal_state": "completed",
        "completed_tasks": ["planning_loop_eval_initial", "planning_loop_eval_follow_up"],
        "remaining_tasks": [],
        "blocked_tasks": [],
        "failed_tasks": [],
        "task_buckets": {"pending": [], "running": [], "completed": [], "blocked": [], "failed": [], "cancelled": []},
    }
    evaluator = SpyEvaluator(
        [
            {
                "schema": "zero.engineering_task.adaptive_planning_decision.v1",
                "decision": "replan",
                "reason": "evaluator_requested_replan",
                "reasons": ["evaluator_requested_replan"],
                "terminal": False,
                "replan_requested": True,
                "deterministic": True,
            },
            {
                "schema": "zero.engineering_task.adaptive_planning_decision.v1",
                "decision": "complete",
                "reason": "evaluator_marked_complete",
                "reasons": ["evaluator_marked_complete"],
                "terminal": True,
                "replan_requested": False,
                "deterministic": True,
            },
        ]
    )
    planner = FakePlanner([[initial], [follow_up]])

    result = EngineeringPlanningLoop(
        repo_root=tmp_path,
        planner=planner,
        continuation_coordinator=SpyCoordinator([incomplete_lifecycle, completed_lifecycle]),
        adaptive_evaluator=evaluator,
        max_replans=1,
    ).run(_payload("planning_loop_eval"))

    assert result["ok"] is True
    assert len(evaluator.calls) == 2
    assert len(planner.calls) == 2
    assert planner.calls[1]["context"]["planning_reason"] == "evaluator_requested_replan"
    assert result["replans"][0]["reason"] == "evaluator_requested_replan"
    assert result["adaptive_planning_decisions"][0]["decision"] == "replan"
    assert result["goal_lifecycle"]["adaptive_planning_decisions"][0]["reason"] == "evaluator_requested_replan"
    assert result["goal_lifecycle"]["latest_adaptive_planning_decision"]["decision"] == "complete"


def test_completed_goal_stops_cleanly(tmp_path: Path) -> None:
    planner = FakePlanner(
        [
            [
                _write_step("planning_loop_complete_one", "workspace/planning_loop_complete_one.txt", "one\n"),
                _write_step("planning_loop_complete_two", "workspace/planning_loop_complete_two.txt", "two\n"),
            ],
            [_write_step("planning_loop_complete_unwanted", "workspace/planning_loop_complete_unwanted.txt", "unwanted\n")],
        ]
    )

    result = EngineeringPlanningLoop(repo_root=tmp_path, planner=planner, max_replans=2).run(_payload("planning_loop_complete"))

    assert result["ok"] is True
    assert result["goal_state"] == "completed"
    assert result["replan_count"] == 0
    assert len(planner.calls) == 1
    assert result["goal_lifecycle"]["remaining_tasks"] == []
    assert (tmp_path / "workspace/planning_loop_complete_two.txt").read_text(encoding="utf-8") == "two\n"
    assert not (tmp_path / "workspace/planning_loop_complete_unwanted.txt").exists()
