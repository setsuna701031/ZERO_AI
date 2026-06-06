from __future__ import annotations

from core.tasks.engineering_adaptive_planner import EngineeringAdaptivePlanner
from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository


def _goal() -> dict:
    return {
        "goal_id": "goal_1",
        "summary": "Build demo system",
        "payload": {"goal": "Build demo system", "task_type": "engineering_task"},
    }


def _runtime(*, ok: bool, state: str, goal_state: str, remaining=None, failed=None, blocked=None) -> dict:
    return {
        "ok": ok,
        "state": state,
        "iterations": [
            {
                "continuation_result": {
                    "goal_lifecycle": {
                        "goal_id": "goal_1",
                        "goal_state": goal_state,
                        "completed_tasks": ["goal_1_breakdown"],
                        "remaining_tasks": list(remaining or []),
                        "failed_tasks": list(failed or []),
                        "blocked_tasks": list(blocked or []),
                    }
                }
            }
        ],
    }


def test_v2_decision_explains_confidence_and_evidence() -> None:
    decision = EngineeringAdaptivePlanner().decide_next_action(
        goal=_goal(),
        runtime_result=_runtime(
            ok=True,
            state="running",
            goal_state="next_task_generated",
            remaining=["goal_1_result"],
        ),
    )

    assert decision["schema"].endswith(".v2")
    assert decision["decision"] == "continue"
    assert decision["confidence"] == decision["confidence_score"]["score"]
    assert decision["confidence_score"]["level"] in {"medium", "high"}
    assert decision["decision_reasoning"]["selected"] == "continue"
    assert decision["decision_reasoning"]["facts"]["remaining_task_count"] == 1
    assert [item["evidence_id"] for item in decision["evidence_chain"]] == [
        f"evidence_{index}" for index in range(1, len(decision["evidence_chain"]) + 1)
    ]
    assert any(item["kind"] == "remaining_work" for item in decision["evidence_chain"])


def test_v2_replan_payload_preserves_completed_work_and_scopes_reconsideration() -> None:
    decision = EngineeringAdaptivePlanner().decide_next_action(
        goal=_goal(),
        runtime_result=_runtime(
            ok=False,
            state="replan",
            goal_state="failed",
            remaining=["goal_1_verify"],
            failed=["missing_output"],
        ),
        runtime_root_cause={"stop_reason": "missing_output"},
    )

    request = decision["replan_request"]
    assert decision["decision"] == "replan"
    assert request["schema"].endswith(".v2")
    assert request["replan_payload"]["preserve"]["completed_tasks"] == ["goal_1_breakdown"]
    assert request["replan_payload"]["reconsider"]["failed_tasks"] == ["missing_output"]
    assert request["replan_payload"]["reconsider"]["remaining_tasks"] == ["goal_1_verify"]
    assert request["replan_payload"]["constraints"]["execute_tasks"] is False
    assert request["root_cause_report"]["classification"] == "recoverable"
    assert request["evidence_chain"]


def test_v2_blocked_root_cause_report_identifies_primary_cause_and_affected_tasks() -> None:
    issue = {"issue_id": "blocker-1", "severity": "critical", "blocks_current_task": True}
    decision = EngineeringAdaptivePlanner().decide_next_action(
        goal=_goal(),
        runtime_result=_runtime(
            ok=False,
            state="blocked",
            goal_state="blocked",
            blocked=["goal_1_result"],
        ),
        runtime_root_cause={"stop_reason": "authority_denied"},
        issue_summary={"blocking_issues": [issue]},
    )

    report = decision["root_cause_report"]
    assert decision["decision"] == "blocked"
    assert report["classification"] == "blocked"
    assert report["primary_cause"] == "authority_denied"
    assert report["affected_tasks"] == ["goal_1_result"]
    assert report["blocking_issues"] == [issue]
    assert report["recommended_action"] == "stop_and_report"
    assert report["evidence_ids"]


def test_v2_continuation_template_is_persisted_only_by_goal_loop(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "goal_1", "summary": "Build demo system"})
    decision = EngineeringAdaptivePlanner().decide_next_action(
        goal=_goal(),
        runtime_result=_runtime(
            ok=True,
            state="running",
            goal_state="next_task_generated",
            remaining=["goal_1_result"],
        ),
    )

    assert repository.list_goals() == [repository.load_goal("goal_1")]

    class Runner:
        def run_goal(self, goal_id: str) -> dict:
            return {
                "ok": True,
                "goal_id": goal_id,
                "runtime_result": {"state": "running"},
                "adaptive_decision": decision,
            }

    result = EngineeringGoalLoop(
        repo_root=tmp_path,
        repository=repository,
        runner=Runner(),
    ).run_until_terminal("goal_1", max_cycles=1)

    work_item = result["cycles"][0]["continuation_work_item"]
    record = repository.load_goal(work_item["goal_id"])
    assert record["payload"]["continuation_objective"] == "Build demo system"
    assert record["payload"]["continuation_acceptance"]["goal_state"] == "completed"
    assert record["metadata"]["work_item_template"]["remaining_tasks"] == ["goal_1_result"]
    assert record["metadata"]["adaptive_evidence_chain"]
