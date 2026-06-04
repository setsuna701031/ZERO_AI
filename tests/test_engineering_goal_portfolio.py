from __future__ import annotations

import ast
import copy
from pathlib import Path

from core.tasks.engineering_goal_portfolio import EngineeringGoalPortfolio, EngineeringGoalRecord


REPO_ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO_FILE = REPO_ROOT / "core/tasks/engineering_goal_portfolio.py"


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
    tree = ast.parse(PORTFOLIO_FILE.read_text(encoding="utf-8"))
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
    tree = ast.parse(PORTFOLIO_FILE.read_text(encoding="utf-8"))

    def name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

    return {name(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}


def test_portfolio_selects_highest_priority_runnable_goal() -> None:
    decision = EngineeringGoalPortfolio().decide_next_goal(
        [
            _goal("low", priority=1),
            _goal("high", priority=10),
            _goal("middle", priority=5),
        ]
    )

    assert decision["decision"] == "select_goal"
    assert decision["selected_goal_id"] == "high"
    assert decision["reason"] == "highest_priority_runnable_goal"


def test_portfolio_skips_completed_blocked_cancelled_goals() -> None:
    decision = EngineeringGoalPortfolio().decide_next_goal(
        [
            _goal("done", priority=100, status="completed"),
            _goal("stuck", priority=99, status="blocked"),
            _goal("cancelled", priority=98, status="cancelled"),
            _goal("ready", priority=1, status="running"),
        ]
    )

    assert decision["selected_goal_id"] == "ready"
    skipped = {item["goal_id"]: item["reason"] for item in decision["skipped_goals"]}
    assert skipped["done"] == "goal_status_completed"
    assert skipped["stuck"] == "goal_status_blocked"
    assert skipped["cancelled"] == "goal_status_cancelled"


def test_portfolio_uses_deterministic_tie_breaking() -> None:
    goals = [
        _goal("b_goal", priority=5, created_at=1),
        _goal("a_goal", priority=5, created_at=1),
        _goal("older_goal", priority=5, created_at=0),
    ]

    decision = EngineeringGoalPortfolio().decide_next_goal(goals)

    assert decision["selected_goal_id"] == "older_goal"
    assert EngineeringGoalPortfolio().decide_next_goal(list(reversed(goals)))["selected_goal_id"] == "older_goal"


def test_portfolio_returns_no_runnable_goal_cleanly() -> None:
    decision = EngineeringGoalPortfolio().decide_next_goal(
        [
            _goal("done", status="completed"),
            _goal("stuck", status="blocked"),
        ]
    )

    assert decision == {
        "schema": "zero.engineering_goal_portfolio.decision.v1",
        "selected_goal_id": "",
        "decision": "no_runnable_goal",
        "reason": "no_runnable_goals_available",
        "skipped_goals": [
            {"goal_id": "done", "status": "completed", "reason": "goal_status_completed"},
            {"goal_id": "stuck", "status": "blocked", "reason": "goal_status_blocked"},
        ],
    }


def test_portfolio_routes_selected_goal_to_planning_loop() -> None:
    planning_loop = SpyPlanningLoop()
    result = EngineeringGoalPortfolio().route_selected_goal(
        [
            EngineeringGoalRecord.from_mapping(_goal("first", priority=1)),
            EngineeringGoalRecord.from_mapping(_goal("selected", priority=9)),
        ],
        planning_loop=planning_loop,
    )

    assert result["ok"] is True
    assert result["portfolio_decision"]["selected_goal_id"] == "selected"
    assert result["planning_result"]["goal_id"] == "selected"
    expected_payload = _goal("selected", priority=9)["payload"]
    expected_payload["task_type"] = "engineering_task"
    assert planning_loop.calls == [expected_payload]
    assert result["execution_path"]["portfolio_selects_only"] is True
    assert result["execution_path"]["existing_planning_loop_reused"] is True


def test_portfolio_does_not_execute_directly() -> None:
    calls = _calls()

    assert "run_engineering_task" not in calls
    assert "submit_work_package" not in calls
    assert not any(call.endswith(".submit") for call in calls)
    assert "WorkPackageScheduler" not in calls
    assert "EngineeringTaskRunner" not in calls


def test_portfolio_does_not_import_task_runner_or_memory_store() -> None:
    imports = _imports()

    assert "EngineeringTaskRunner" not in imports
    assert "core.tasks.engineering_task_runner" not in imports
    assert "run_engineering_task" not in imports
    assert "EngineeringMemoryStore" not in imports
    assert "core.tasks.engineering_memory_store" not in imports
