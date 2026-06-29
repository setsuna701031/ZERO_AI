from __future__ import annotations

from core.runtime.runtime_session_resume import (

    RESUMABLE_TASK_STATUSES,
    RuntimeSessionResume,
    is_resumable_task_status,
    is_terminal_task_status,
    stable_resume_fingerprint,
)
from core.runtime.runtime_task_continuation import RuntimeTaskContinuation
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
import pytest

pytestmark = [pytest.mark.contract]



def test_runtime_session_resume_contract_seal(tmp_path):
    runtime = RuntimeSessionResume(workspace_root=tmp_path, storage_path=tmp_path / "resume.json")
    plan = runtime.build_resume_plan(tasks=[{"task_id": "task-a", "status": "running"}], session_id="seal-session")

    assert plan["ok"] is True
    assert plan["action"] == "resume_tasks"
    assert plan["resume_policy"]["scheduler_should_requeue_runnable"] is True
    assert plan["resume_policy"]["scheduler_should_keep_blocked_waiting"] is True


def test_runtime_session_resume_status_boundary_seal():
    assert is_resumable_task_status("running") is True
    assert is_resumable_task_status("review_required") is True
    assert is_terminal_task_status("finished") is True
    assert is_terminal_task_status("failed") is True
    assert "running" in RESUMABLE_TASK_STATUSES
    assert "review_required" in RESUMABLE_TASK_STATUSES


def test_runtime_session_resume_fingerprint_is_stable():
    left = stable_resume_fingerprint({"b": 2, "a": 1})
    right = stable_resume_fingerprint({"a": 1, "b": 2})
    assert left == right
    assert len(left) == 64


def test_runtime_session_resume_preserves_replan_lineage_after_stop(tmp_path):
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal(
        {
            "goal_id": "goal_replan_resume",
            "summary": "create workspace/report.txt",
            "payload": {
                "target_path": "workspace/report.txt",
                "verify_contains": "missing-from-output",
            },
        }
    )

    result = EngineeringGoalLoop(repo_root=tmp_path, repository=repository).run_until_terminal(
        "goal_replan_resume",
        max_cycles=1,
        max_replans=1,
    )
    replan_record = result["cycles"][0]["replan_record"]
    replan_task = {
        "task_id": "replan:goal_replan_resume:0",
        "goal_id": "goal_replan_resume",
        "status": "running",
        "source_goal_id": replan_record["source_goal_id"],
        "cycle_index": replan_record["cycle_index"],
        "evidence_ref": replan_record["evidence_ref"],
        "decision_evidence_id": replan_record["decision_evidence_id"],
        "evidence_refs": replan_record["evidence_refs"],
        "replan_record": replan_record,
        "next_runtime_request": replan_record["next_runtime_request"],
    }

    runtime = RuntimeSessionResume(workspace_root=tmp_path, storage_path=tmp_path / "resume.json")
    runtime.create_session_record(session_id="replan-stop", tasks=[replan_task, dict(replan_task)])
    resumed = RuntimeSessionResume(workspace_root=tmp_path, storage_path=tmp_path / "resume.json")
    plan = resumed.build_resume_plan(session_id="replan-stop")
    continuation = RuntimeTaskContinuation().build_plan([replan_task, dict(replan_task)]).to_dict()

    lineage = plan["lineage_by_task_id"]["replan:goal_replan_resume:0"]
    assert result["ok"] is False
    assert result["cycles"][0]["adaptive_decision"] == "replan"
    assert result["goal_completion_authority_result"]["accepted"] is False
    assert plan["task_ids"] == ["replan:goal_replan_resume:0"]
    assert continuation["requeue_task_ids"] == ["replan:goal_replan_resume:0"]
    assert continuation["duplicate_task_ids"] == ["replan:goal_replan_resume:0"]
    assert lineage["source_goal_id"] == "goal_replan_resume"
    assert lineage["cycle_index"] == 0
    assert lineage["evidence_ref"] == replan_record["evidence_ref"]
    assert lineage["decision_evidence_id"] == replan_record["decision_evidence_id"]
    assert replan_record["task_id"] == "replan:goal_replan_resume:0"
    assert replan_record["authority_state"] == "completion_authority_not_granted"


def test_runtime_session_resume_continuation_stop_resume_executes_next_goal(tmp_path):
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "goal_workspace_file", "summary": "create workspace/example.txt"})

    first = EngineeringGoalLoop(repo_root=tmp_path, repository=repository).run_until_terminal(
        "goal_workspace_file",
        max_cycles=1,
        max_continuations=1,
    )
    work_item = first["cycles"][0]["continuation_work_item"]
    continuation_goal_id = work_item["goal_id"]
    continuation_task = {
        "task_id": continuation_goal_id,
        "goal_id": continuation_goal_id,
        "status": "queued",
        "source_goal_id": work_item["source_goal_id"],
        "cycle_index": work_item["cycle_index"],
        "decision_evidence_id": work_item["decision_evidence_id"],
        "continuation_work_item": work_item,
    }

    runtime = RuntimeSessionResume(workspace_root=tmp_path, storage_path=tmp_path / "resume.json")
    runtime.create_session_record(session_id="continuation-stop", tasks=[continuation_task, dict(continuation_task)])
    plan = RuntimeSessionResume(workspace_root=tmp_path, storage_path=tmp_path / "resume.json").build_resume_plan(
        session_id="continuation-stop"
    )
    second = EngineeringGoalLoop(repo_root=tmp_path, repository=repository).run_until_terminal(
        continuation_goal_id,
        max_cycles=1,
        max_continuations=1,
    )

    lineage = plan["lineage_by_task_id"][continuation_goal_id]
    assert first["ok"] is True
    assert plan["task_ids"] == [continuation_goal_id]
    assert lineage["source_goal_id"] == "goal_workspace_file"
    assert lineage["cycle_index"] == 0
    assert lineage["decision_evidence_id"] == work_item["decision_evidence_id"]
    assert work_item["task_id"] == continuation_goal_id
    assert work_item["evidence_ref"] == work_item["decision_evidence_id"]
    assert work_item["decision_evidence_id"] in work_item["evidence_refs"]
    assert work_item["authority_state"] == "completion_authority_accepted"
    assert second["ok"] is True
    assert second["goal_completion_authority_result"]["accepted"] is True
    assert (tmp_path / "workspace/example.txt").is_file()
    assert (tmp_path / "workspace/example_next.txt").is_file()
    assert repository.load_goal("goal_workspace_file__continuation_1__continuation_2") is None


def test_runtime_session_resume_complete_after_stop_does_not_bypass_authority(tmp_path):
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "goal_resume_complete", "summary": "create workspace/example.txt"})
    task = {"task_id": "goal_resume_complete", "goal_id": "goal_resume_complete", "status": "running"}

    runtime = RuntimeSessionResume(workspace_root=tmp_path, storage_path=tmp_path / "resume.json")
    runtime.create_session_record(session_id="complete-stop", tasks=[task])
    plan = RuntimeSessionResume(workspace_root=tmp_path, storage_path=tmp_path / "resume.json").build_resume_plan(
        session_id="complete-stop"
    )
    missing_evidence = GoalCompletionAuthority().complete_goal(
        goal_id="goal_resume_complete",
        evidence_refs=[],
        all_subgoals_completed=True,
        reason="resume_missing_evidence",
    )
    result = EngineeringGoalLoop(repo_root=tmp_path, repository=repository).run_until_terminal(
        "goal_resume_complete",
        max_cycles=1,
    )

    assert plan["task_ids"] == ["goal_resume_complete"]
    assert missing_evidence.accepted is False
    assert missing_evidence.completed is False
    assert result["ok"] is True
    assert result["goal_completion_authority_result"]["accepted"] is True
