from __future__ import annotations

import inspect

from core.control.task_lifecycle_monitor import TaskLifecycleMonitor
from core.evidence.decision_evidence import DecisionEvidenceRepository, build_decision_evidence
from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository


def _adaptive(decision: str, outcome_class: str, next_action: str) -> dict:
    return {
        "decision": decision,
        "reason": f"{decision}_reason",
        "outcome_class": outcome_class,
        "next_action": next_action,
        "confidence": 0.8,
        "evidence_chain": [{"evidence_id": "runtime_fact_1"}],
        "adaptive_planning_record": {
            "outcome_class": outcome_class,
            "decision_reason": f"runtime_outcome_{outcome_class}",
            "next_action": next_action,
        },
        "continuation_plan": {
            "next_runtime_request": {"payload": {"goal": "Continue bounded work"}},
        },
        "replan_request": {"reason": "recoverable_failure"},
    }


class SequenceRunner:
    def __init__(self, decisions: list[dict]) -> None:
        self.decisions = decisions
        self.index = 0

    def run_goal(self, goal_id: str, *, goal_lineage=None) -> dict:
        adaptive = self.decisions[self.index]
        self.index += 1
        task_id = f"task_{self.index}"
        return {
            "ok": adaptive["decision"] != "replan",
            "goal_id": goal_id,
            "runtime_result": {
                "ok": adaptive["decision"] != "replan",
                "state": "replan" if adaptive["decision"] == "replan" else "running",
                "iterations": [
                    {
                        "continuation_result": {
                            "goal_lifecycle": {
                                "goal_state": "failed" if adaptive["decision"] == "replan" else "next_task_generated",
                                "failed_tasks": [task_id] if adaptive["decision"] == "replan" else [],
                            },
                            "latest_result": {"task_id": task_id},
                        }
                    }
                ],
            },
            "adaptive_decision": adaptive,
        }


def test_decision_evidence_persists_required_fields_and_explicit_missing_confidence(tmp_path) -> None:
    record = build_decision_evidence(
        cycle={
            "goal_id": "goal_1",
            "cycle_index": 0,
            "runner_result": {
                "runtime_result": {
                    "state": "replan",
                    "iterations": [{"continuation_result": {"latest_result": {"task_id": "task_1"}}}],
                }
            },
            "adaptive_decision_record": {
                "decision": "replan",
                "reason": "recoverable",
                "outcome_class": "recoverable_failure",
                "next_action": "request_replan",
            },
            "adaptive_planning_record": {
                "outcome_class": "recoverable_failure",
                "decision_reason": "runtime_outcome_recoverable_failure",
                "next_action": "request_replan",
            },
        }
    )
    persisted = DecisionEvidenceRepository(tmp_path).save(record)

    required = {
        "decision_id",
        "goal_id",
        "task_id",
        "source_stage",
        "observed_event",
        "outcome_class",
        "decision",
        "decision_reason",
        "confidence_unavailable_reason",
        "next_action",
        "evidence_refs",
        "created_at",
    }
    assert required.issubset(persisted)
    assert DecisionEvidenceRepository(tmp_path).find_by_task_id("task_1") == [persisted]
    assert DecisionEvidenceRepository(tmp_path).list_records()[0]["next_action"] == "request_replan"


def test_goal_loop_persists_replan_and_links_continuation_decision_evidence(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "goal_continue", "summary": "Continue then replan"})
    evidence_repository = DecisionEvidenceRepository(tmp_path)
    loop = EngineeringGoalLoop(
        repo_root=tmp_path,
        repository=repository,
        decision_evidence_repository=evidence_repository,
        runner=SequenceRunner(
            [
                _adaptive("continue", "partial_success", "create_followup_goal"),
                _adaptive("replan", "recoverable_failure", "request_replan"),
            ]
        ),
    ).run_until_terminal("goal_continue", max_cycles=2, max_replans=1, max_continuations=1)

    assert loop["stop_reason"] == "replan"
    assert len(evidence_repository.list_records()) == 2
    continuation = loop["cycles"][0]["continuation_work_item"]
    assert continuation["decision_evidence_id"] == loop["cycles"][0]["decision_evidence"]["decision_id"]
    saved_continuation = repository.load_goal(continuation["goal_id"])
    assert saved_continuation["metadata"]["decision_evidence_id"] == continuation["decision_evidence_id"]
    assert loop["cycles"][1]["replan_record"]["decision_evidence_id"] == loop["cycles"][1]["decision_evidence"]["decision_id"]


def test_lifecycle_monitor_exposes_persisted_decision_evidence_read_only(tmp_path) -> None:
    evidence_repository = DecisionEvidenceRepository(tmp_path)
    evidence_repository.save(
        {
            "decision_id": "decision_1",
            "goal_id": "goal_1",
            "task_id": "task_1",
            "source_stage": "engineering_goal_loop",
            "observed_event": {"runtime_state": "replan"},
            "outcome_class": "recoverable_failure",
            "decision": "replan",
            "decision_reason": "runtime_outcome_recoverable_failure",
            "confidence": 0.8,
            "next_action": "request_replan",
            "evidence_refs": [],
            "created_at": 1.0,
        }
    )

    class Repository:
        def get_task(self, task_id):
            return {"task_id": task_id, "status": "failed"}

    snapshot = TaskLifecycleMonitor(Repository(), evidence_repository).inspect("task_1")

    assert snapshot["decision_evidence"][0]["decision_id"] == "decision_1"
    source = inspect.getsource(__import__("core.evidence.decision_evidence", fromlist=["DecisionEvidenceRepository"]))
    assert "core.runtime" not in source
    assert "core.tools" not in source
    assert ".execute(" not in source
