from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.tasks.adaptive_planning_foundation import (
    ADAPTIVE_ACTIONS,
    OUTCOME_CLASSES,
    evaluate_runtime_outcome,
)
from core.tasks.engineering_adaptive_planner import EngineeringAdaptivePlanner
from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("runtime_result", "progress", "outcome_class", "next_action"),
    [
        ({"ok": True, "state": "complete"}, {"complete": True}, "success", "stop"),
        ({"ok": True, "state": "running"}, {}, "partial_success", "create_followup_goal"),
        ({"ok": False, "state": "replan"}, {"recoverable_failure": True}, "recoverable_failure", "request_replan"),
        ({"ok": False, "state": "failed"}, {}, "unrecoverable_failure", "stop"),
        ({"ok": False, "state": "blocked"}, {"blocking_failure": True}, "blocked", "stop"),
        ({"ok": True, "state": "waiting"}, {}, "waiting", "continue_current_plan"),
    ],
)
def test_runtime_outcomes_are_normalized(runtime_result, progress, outcome_class, next_action) -> None:
    record = evaluate_runtime_outcome(runtime_result, progress=progress, previous_goal="goal_1", previous_step="step_1")

    assert record["outcome_class"] == outcome_class
    assert record["next_action"] == next_action
    assert record["outcome_class"] in OUTCOME_CLASSES
    assert record["next_action"] in ADAPTIVE_ACTIONS
    assert record["previous_goal"] == "goal_1"
    assert record["previous_step"] == "step_1"


def test_evaluation_refuses_exhausted_replan_and_continuation_explicitly() -> None:
    replan = evaluate_runtime_outcome(
        {"ok": False, "state": "replan"},
        progress={"recoverable_failure": True},
        replan_count=1,
        max_replans=1,
    )
    continuation = evaluate_runtime_outcome(
        {"ok": True, "state": "running"},
        continuation_count=2,
        max_continuations=2,
    )

    assert replan["next_action"] == "stop"
    assert replan["refusal_reason"] == "max_replans_exhausted"
    assert continuation["next_action"] == "stop"
    assert continuation["refusal_reason"] == "max_continuations_exhausted"


class _Runner:
    def __init__(self, decision: str) -> None:
        self.decision = decision

    def run_goal(self, goal_id: str) -> dict:
        adaptive = {
            "decision": self.decision,
            "reason": f"{self.decision}_reason",
            "next_action": "create_continuation_work_item" if self.decision == "continue" else "create_replan_record",
            "outcome_class": "partial_success" if self.decision == "continue" else "recoverable_failure",
            "adaptive_planning_record": {
                "previous_goal": goal_id,
                "previous_step": "step_1",
                "outcome_class": "partial_success" if self.decision == "continue" else "recoverable_failure",
                "decision_reason": f"{self.decision}_reason",
                "next_action": "create_followup_goal" if self.decision == "continue" else "request_replan",
            },
            "continuation_plan": {
                "goal_id": goal_id,
                "next_runtime_request": {"payload": {"goal": "Continue bounded goal"}},
            },
            "replan_request": {"goal_id": goal_id, "reason": "recoverable_failure"},
        }
        return {"ok": True, "goal_id": goal_id, "runtime_result": {"state": "running"}, "adaptive_decision": adaptive}


def _repository(tmp_path) -> EngineeringGoalRepository:
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "goal_1", "summary": "Bounded goal"})
    return repository


def test_goal_loop_refuses_unbounded_continuation_and_persists_reason(tmp_path) -> None:
    repository = _repository(tmp_path)
    result = EngineeringGoalLoop(repo_root=tmp_path, repository=repository, runner=_Runner("continue")).run_until_terminal(
        "goal_1",
        max_cycles=3,
        max_continuations=0,
    )

    assert result["terminal"] is True
    assert result["stop_reason"] == "max_continuations_exhausted"
    assert result["adaptive_refusal_reason"] == "max_continuations_exhausted"
    record = repository.load_goal("goal_1")["metadata"]["adaptive_planning_record"]
    assert record["decision_reason"] == "max_continuations_exhausted"
    assert record["next_action"] == "stop"


def test_goal_loop_refuses_unbounded_replan_and_persists_reason(tmp_path) -> None:
    repository = _repository(tmp_path)
    result = EngineeringGoalLoop(repo_root=tmp_path, repository=repository, runner=_Runner("replan")).run_until_terminal(
        "goal_1",
        max_replans=0,
    )

    assert result["terminal"] is True
    assert result["stop_reason"] == "max_replans_exhausted"
    assert result["replan_count"] == 0
    assert repository.load_goal("goal_1")["metadata"]["adaptive_planning_record"]["refusal_reason"] == "max_replans_exhausted"


def test_planner_record_is_decision_only_and_runtime_remains_execution_authority() -> None:
    decision = EngineeringAdaptivePlanner().decide_next_action(
        goal={"goal_id": "goal_1"},
        runtime_result={"ok": False, "state": "replan"},
        runtime_root_cause={"stop_reason": "recoverable"},
    )

    assert decision["adaptive_planning_record"]["execution_path"]["executes_tasks"] is False
    assert decision["adaptive_planning_record"]["execution_path"]["persists_records"] is False

    foundation_tree = ast.parse((REPO_ROOT / "core/tasks/adaptive_planning_foundation.py").read_text(encoding="utf-8"))
    goal_loop_source = (REPO_ROOT / "core/tasks/engineering_goal_loop.py").read_text(encoding="utf-8")
    imports = {
        node.module
        for node in ast.walk(foundation_tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(name.startswith("core.runtime") or name.startswith("core.tools") for name in imports)
    assert "self.runner.run_goal" in goal_loop_source
    assert "self.runtime_orchestrator.run" not in goal_loop_source
