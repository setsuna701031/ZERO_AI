from __future__ import annotations

from typing import Any

from core.goals.goal_completion_authority import (
    GOAL_COMPLETION_AUTHORITY_OWNER,
    GOAL_COMPLETION_RESULT_SCHEMA,
    GoalCompletionAuthority,
)
from core.evidence import EvidenceRecord, EvidenceValidator
from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.goals.goal_lineage_contract import attach_goal_lineage, create_root_goal_lineage


class FakeRepository:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {
            "goal-1": attach_goal_lineage(
                {"goal_id": "goal-1", "summary": "demo", "payload": {"goal": "demo"}},
                create_root_goal_lineage(goal_id="goal-1"),
            )
        }

    def load_goal(self, goal_id: str):
        return self.records.get(goal_id)

    def save_goal(self, record: dict[str, Any]) -> dict[str, Any]:
        self.records[record["goal_id"]] = record
        return record

    def update_goal(self, goal_id: str, patch: dict[str, Any]) -> None:
        self.records.setdefault(goal_id, {"goal_id": goal_id}).setdefault("metadata", {}).update(patch.get("metadata", {}))


class FakeRunner:
    def __init__(self) -> None:
        self.decisions = ["continue", "complete"]
        self.index = 0

    def run_goal(self, goal_id: str, *, goal_lineage=None) -> dict[str, Any]:
        decision = self.decisions[min(self.index, len(self.decisions) - 1)]
        self.index += 1
        progress = {
            "remaining_tasks": ["b"] if decision == "continue" else [],
            "completed_tasks": ["a"] if decision == "continue" else ["a", "b"],
            "failed_tasks": [],
            "blocked_tasks": [],
        }
        adaptive_decision = {
            "decision": decision,
            "reason": f"{decision}_reason",
            "progress": progress,
            "continuation_plan": {
                "goal_id": goal_id,
                "next_runtime_request": {"payload": {"goal": "continue demo"}},
                "work_item_template": {"objective": "continue demo", "acceptance": {}},
            } if decision == "continue" else {},
            "adaptive_planning_record": {},
        }
        if decision == "complete":
            evidence = EvidenceValidator().validate(EvidenceRecord(
                "validated-demo", goal_id, None, "test", "ok", "now",
                metadata={**goal_lineage, "goal_lineage": goal_lineage},
            ))
            adaptive_decision["goal_completion_authority_result"] = GoalCompletionAuthority().complete_goal(
                goal_id=goal_id,
                evidence_refs=[evidence],
                all_subgoals_completed=True,
                goal_lineage=goal_lineage,
            )
        return {
            "goal_id": goal_id,
            "action": "run_goal",
            "ok": True,
            "engineering_runtime_contract": {
                "schema": "zero.engineering_runtime_contract.v1",
                "goal_id": goal_id,
                "action": "run_goal",
                "ok": True,
                "runtime_result": {"state": "completed" if decision == "complete" else "running", "ok": True},
                "adaptive_decision": adaptive_decision,
                "runtime_root_cause": {},
                "runtime_request": {},
                "runtime_stdout": "",
                "issue_summary": {},
            },
        }


class FakePersistenceGateway:
    def persist_cycle(self, cycle: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        cycle["adaptive_persistence_gateway"] = {"persisted": True, **kwargs}
        return cycle

    def evidence_chain_summary(self, goal_id: str) -> dict[str, Any]:
        return {"goal_id": goal_id, "validated_count": 1}


def test_engineering_goal_loop_records_observation_delta_and_loop_contract(tmp_path) -> None:
    loop = EngineeringGoalLoop(
        repo_root=tmp_path,
        repository=FakeRepository(),
        runner=FakeRunner(),
        adaptive_persistence_gateway=FakePersistenceGateway(),
    )
    result = loop.run_until_terminal("goal-1", max_cycles=2)
    assert result["terminal"] is True
    assert result["stop_reason"] == "complete"
    assert result["cycles"][0]["adaptive_loop_contract"]["next_cycle_allowed"] is True
    assert result["cycles"][1]["adaptive_loop_contract"]["loop_state"] == "terminal"
    assert result["cycles"][1]["adaptive_delta"]["has_progress"] is True
    assert result["execution_path"]["goal_loop_consumes_adaptive_loop_contract"] is True


def test_non_terminal_feedback_is_not_misclassified_as_terminal(tmp_path) -> None:
    runner = FakeRunner()
    runner.decisions = ["continue"]
    result = EngineeringGoalLoop(
        repo_root=tmp_path,
        repository=FakeRepository(),
        runner=runner,
        adaptive_persistence_gateway=FakePersistenceGateway(),
    ).run_until_terminal("goal-1", max_cycles=1)

    assert result["terminal"] is False
    assert result["stop_reason"] == "max_cycles_reached"
    assert result["cycles"][0]["adaptive_loop_contract"]["next_cycle_allowed"] is True
