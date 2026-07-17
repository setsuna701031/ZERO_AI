from __future__ import annotations

import ast
import copy
from pathlib import Path

from core.tasks.engineering_goal_scheduler import EngineeringGoalScheduler


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_FILE = REPO_ROOT / "core/tasks/engineering_goal_scheduler.py"


def _goal(goal_id: str, *, priority: float = 0, status: str = "pending", created_at: float = 1) -> dict:
    return {
        "goal_id": goal_id,
        "priority": priority,
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "last_result_summary": "",
        "blocked_reason": "waiting" if status == "blocked" else "",
        "planning_refs": {"source": f"plan:{goal_id}"},
        "lifecycle_refs": {"state_path": f"state:{goal_id}"},
        "payload": {
            "goal_id": goal_id,
            "task_id": goal_id,
            "package_id": goal_id,
            "goal": f"Goal {goal_id}",
        },
    }


class SpyPlanningLoop:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def run(self, payload):
        self.calls.append(copy.deepcopy(dict(payload)))
        return {
            "ok": True,
            "schema": "zero.engineering_planning_loop.v1",
            "goal_id": payload["goal_id"],
            "execution_path": {
                "direct_execution": False,
                "new_execution_path": False,
            },
        }


def _imports() -> set[str]:
    tree = ast.parse(SCHEDULER_FILE.read_text(encoding="utf-8"))
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
    tree = ast.parse(SCHEDULER_FILE.read_text(encoding="utf-8"))

    def name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

    return {name(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}


def test_scheduler_runs_highest_priority_goal_via_portfolio() -> None:
    planning_loop = SpyPlanningLoop()
    result = EngineeringGoalScheduler().run_next_goal(
        [
            _goal("low", priority=1),
            _goal("high", priority=10),
            _goal("middle", priority=5),
        ],
        planning_loop=planning_loop,
    )

    assert result["ok"] is True
    assert result["scheduler_decision"]["action"] == "run_next_goal"
    assert result["scheduler_decision"]["selected_goal_id"] == "high"
    assert result["portfolio_decision"]["selected_goal_id"] == "high"
    assert planning_loop.calls[0]["goal_id"] == "high"
    assert result["execution_path"]["scheduler_schedules_only"] is True
    assert result["execution_path"]["direct_execution"] is False


def test_scheduler_pauses_goal() -> None:
    result = EngineeringGoalScheduler().pause_goal([_goal("target")], "target")

    assert result["ok"] is True
    assert result["scheduler_decision"]["action"] == "pause_goal"
    assert result["scheduler_decision"]["selected_goal_id"] == "target"
    assert result["goals"][0]["status"] == "paused"
    assert result["goals"][0]["schedule_refs"]["last_scheduler_action"] == "pause_goal"


def test_scheduler_resumes_goal() -> None:
    result = EngineeringGoalScheduler().resume_goal([_goal("target", status="paused")], "target")

    assert result["ok"] is True
    assert result["scheduler_decision"]["action"] == "resume_goal"
    assert result["goals"][0]["status"] == "pending"
    assert result["goals"][0]["schedule_refs"]["last_scheduler_action"] == "resume_goal"


def test_scheduler_cancels_goal() -> None:
    result = EngineeringGoalScheduler().cancel_goal([_goal("target")], "target")

    assert result["ok"] is True
    assert result["scheduler_decision"]["action"] == "cancel_goal"
    assert result["goals"][0]["status"] == "cancelled"
    assert result["execution_path"]["direct_execution"] is False


def test_scheduler_defers_goal() -> None:
    result = EngineeringGoalScheduler().defer_goal(
        [_goal("target")],
        "target",
        deferred_until="2026-06-05T00:00:00Z",
    )

    assert result["ok"] is True
    assert result["scheduler_decision"]["action"] == "defer_goal"
    assert result["goals"][0]["status"] == "deferred"
    assert result["scheduler_decision"]["deferred_goals"] == [
        {
            "goal_id": "target",
            "status": "deferred",
            "reason": "goal_status_deferred",
            "deferred_until": "2026-06-05T00:00:00Z",
        }
    ]


def test_scheduler_returns_no_runnable_goal_cleanly() -> None:
    planning_loop = SpyPlanningLoop()
    result = EngineeringGoalScheduler().run_next_goal(
        [
            _goal("done", priority=10, status="completed"),
            _goal("paused", priority=9, status="paused"),
            _goal("deferred", priority=8, status="deferred"),
        ],
        planning_loop=planning_loop,
    )

    assert result["ok"] is False
    assert result["scheduler_decision"]["selected_goal_id"] == ""
    assert result["scheduler_decision"]["action"] == "no_runnable_goal"
    assert result["scheduler_decision"]["reason"] == "no_runnable_goals_available"
    assert result["scheduler_decision"]["deferred_goals"][0]["goal_id"] == "deferred"
    skipped = {item["goal_id"]: item["reason"] for item in result["scheduler_decision"]["skipped_goals"]}
    assert skipped["done"] == "goal_status_completed"
    assert skipped["paused"] == "goal_status_paused"
    assert planning_loop.calls == []


def test_scheduler_routes_selected_goal_to_planning_loop() -> None:
    planning_loop = SpyPlanningLoop()
    result = EngineeringGoalScheduler().run_next_goal(
        [
            _goal("first", priority=1),
            _goal("selected", priority=9),
            _goal("paused", priority=99, status="paused"),
        ],
        planning_loop=planning_loop,
    )

    assert result["ok"] is True
    assert result["scheduler_decision"]["selected_goal_id"] == "selected"
    assert result["planning_result"]["goal_id"] == "selected"
    expected_payload = _goal("selected", priority=9)["payload"]
    expected_payload["task_type"] = "engineering_task"
    assert planning_loop.calls == [expected_payload]
    assert result["portfolio_result"]["execution_path"]["existing_planning_loop_reused"] is True


def test_scheduler_does_not_execute_directly() -> None:
    calls = _calls()

    assert "run_engineering_task" not in calls
    assert "submit_work_package" not in calls
    assert not any(call.endswith(".submit") for call in calls)
    assert "WorkPackageScheduler" not in calls
    assert "EngineeringTaskRunner" not in calls
    assert "save_record" not in calls
    assert not any(call.endswith(".plan") for call in calls)


def test_scheduler_does_not_import_task_runner_or_memory_store() -> None:
    imports = _imports()

    assert "EngineeringTaskRunner" not in imports
    assert "core.tasks.engineering_task_runner" not in imports
    assert "run_engineering_task" not in imports
    assert "EngineeringMemoryStore" not in imports
    assert "core.tasks.engineering_memory_store" not in imports
