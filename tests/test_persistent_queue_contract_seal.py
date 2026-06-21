from __future__ import annotations

import copy

import pytest

from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.runtime.persistent_queue_contract import extract_queue_lineage
from core.runtime.persistent_runtime_orchestrator import PersistentRuntimeOrchestrator
from core.runtime.runtime_session_resume import RuntimeSessionResume
from core.runtime.runtime_task_continuation import RuntimeTaskContinuation
from core.runtime.work_package_queue import RuntimePackageQueue, RuntimePackageQueueError
from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.scheduler_core.task_scheduler_queue import ScheduledTask, TaskSchedulerQueue


def _lineage(**overrides):
    payload = {
        "goal_id": "goal-queue",
        "source_goal_id": "goal-source",
        "cycle_index": 2,
        "task_id": "task-queue",
        "continuation_goal_id": "goal-continuation",
        "continuation_task_id": "task-continuation",
        "replan_request_id": "replan-request-1",
        "evidence_ref": "evidence-1",
        "evidence_refs": ["evidence-1", "decision-1"],
        "decision_evidence_id": "decision-1",
        "authority_state": "completion_authority_not_granted",
    }
    payload.update(overrides)
    return payload


def test_runtime_queue_lineage_seal_and_semantic_duplicate_are_idempotent(tmp_path):
    queue = RuntimePackageQueue(repo_root=tmp_path)
    first = queue.enqueue({"package_id": "package-1", **_lineage()})
    duplicate = queue.enqueue(
        {
            "package_id": "package-2",
            **_lineage(task_id="different-task", evidence_ref="forged", evidence_refs=["forged"]),
        }
    )

    assert len(queue.list_packages()) == 1
    assert duplicate["package_id"] == "package-1"
    assert duplicate["queue_admission"]["result"] == "duplicate_idempotent"
    assert duplicate["queue_admission"]["matched_identity"] == {
        "continuation_task_id": "task-continuation",
        "continuation_goal_id": "goal-continuation",
        "replan_request_id": "replan-request-1",
    }
    assert duplicate["evidence_ref"] == first["evidence_ref"] == "evidence-1"
    assert duplicate["evidence_refs"] == first["evidence_refs"]
    assert duplicate["authority_state"] == first["authority_state"]


def test_runtime_planning_retry_preserves_lineage_without_empty_overwrite(tmp_path):
    queue = RuntimePackageQueue(repo_root=tmp_path)
    queue.enqueue({"package_id": "package-plan", **_lineage()})
    snapshot = {
        "planning_status": "planned",
        "runtime_queue_item": {"task_id": "task-queue", "steps": [{"id": "step-1"}]},
    }
    first = queue.record_planning("package-plan", snapshot)
    retry = queue.record_planning(
        "package-plan",
        {
            **snapshot,
            "runtime_queue_item": {
                "task_id": "task-queue",
                "steps": [{"id": "duplicate-step"}],
                "evidence_ref": "",
                "evidence_refs": [],
                "authority_state": "",
            },
        },
    )

    assert extract_queue_lineage(first["runtime_queue_item"]) == _lineage()
    assert extract_queue_lineage(retry["runtime_queue_item"]) == _lineage()
    assert retry["runtime_queue_item"]["steps"] == [{"id": "step-1"}]


def test_scheduler_queue_retry_and_semantic_duplicate_do_not_replace_evidence():
    queue = TaskSchedulerQueue()
    original = ScheduledTask(task_id="task-queue", payload={**_lineage(), "attempt": 1})
    assert queue.enqueue(original) is True

    retry = ScheduledTask(
        task_id="task-queue",
        payload={**_lineage(evidence_ref="forged", evidence_refs=["forged"]), "attempt": 2},
    )
    assert queue.enqueue(retry, overwrite=True) is True
    stored = queue.get_task("task-queue")
    assert stored is not None
    assert stored.payload["attempt"] == 2
    assert stored.payload["evidence_ref"] == "evidence-1"
    assert stored.payload["evidence_refs"] == ["evidence-1", "decision-1"]

    semantic_duplicate = ScheduledTask(
        task_id="another-task",
        payload=_lineage(task_id="another-task"),
    )
    assert queue.enqueue(semantic_duplicate) is False
    assert queue.last_admission_result["result"] == "duplicate_idempotent"
    assert len(queue) == 1


def test_blocked_queue_item_cannot_create_replan_continue_or_complete(tmp_path):
    queue = RuntimePackageQueue(repo_root=tmp_path)
    queue._write(
        {
            "package_id": "package-blocked",
            "task_id": "task-blocked",
            "status": "running",
            "runtime_lifecycle_state": "executing",
            "runtime_queue_item": {"task_id": "task-blocked", "steps": []},
        }
    )
    rejected = queue.record_replan_request(
        "package-blocked",
        {
            "request_id": "blocked-replan",
            "root_cause": "policy_denied",
            "next_action": "replan",
        },
    )

    assert not rejected.get("replan_requests")
    assert rejected["replan_rejections"][0]["failure_class"] == "blocked"
    assert not rejected.get("continuation_work_item")
    assert rejected["status"] == "running"
    with pytest.raises(RuntimePackageQueueError, match="replan_append_requires_admitted_request"):
        queue.append_replan_steps(
            "package-blocked",
            request={"request_id": "blocked-replan"},
            steps=[{"id": "forbidden"}],
            replan_snapshot={},
        )


def test_incomplete_resume_snapshot_is_blocked_and_never_requeued(tmp_path):
    class Repository:
        def __init__(self, task):
            self.task = copy.deepcopy(task)

        def list_tasks(self):
            return [copy.deepcopy(self.task)]

        def save_task(self, task):
            self.task = copy.deepcopy(task)
            return self.task

    class Scheduler:
        def __init__(self):
            self.calls = []

        def submit_existing_task(self, task_id):
            self.calls.append(task_id)
            return {"ok": True, "task_id": task_id, "status": "queued"}

    task = {"status": "running", **_lineage()}
    store = tmp_path / "resume.json"
    RuntimeSessionResume(workspace_root=tmp_path, storage_path=store).create_session_record(
        session_id="queue-resume", tasks=[task, copy.deepcopy(task)]
    )
    repository = Repository(task)
    scheduler = Scheduler()
    orchestrator = PersistentRuntimeOrchestrator(
        repo_root=tmp_path,
        workspace_dir=tmp_path / "workspace",
        resume_store_path=store,
        auto_create_resume_record=False,
    )

    first = orchestrator.resume_last_session(task_repository=repository, scheduler=scheduler)
    second = orchestrator.resume_last_session(task_repository=repository, scheduler=scheduler)

    assert first["requeued_task_ids"] == []
    assert first["waiting_task_ids"] == ["task-queue"]
    assert scheduler.calls == []
    assert second["action"] == "idempotent_resume_skip"
    assert second["requeued_task_ids"] == []


def test_continuation_identity_dedupes_without_creating_a_new_goal():
    first = {
        "task_id": "task-continuation",
        "status": "queued",
        "continuation_goal_id": "goal-continuation",
        "continuation_task_id": "task-continuation",
        "continuation_work_item": _lineage(),
    }
    duplicate = {
        **copy.deepcopy(first),
        "task_id": "renamed-task",
    }
    plan = RuntimeTaskContinuation().build_plan([first, duplicate]).to_dict()

    assert plan["requeue_task_ids"] == ["task-continuation"]
    assert plan["duplicate_task_ids"] == ["renamed-task"]


def test_queue_has_package_only_completion_scope_and_missing_evidence_cannot_complete_goal(tmp_path):
    queue = RuntimePackageQueue(repo_root=tmp_path)
    record = queue.enqueue({"package_id": "package-authority", **_lineage()})
    result = GoalCompletionAuthority().complete_goal(
        goal_id="goal-queue",
        from_state="active",
        evidence_refs=[],
        all_subgoals_completed=True,
        reason="queue_claim_without_evidence",
    )

    assert record["queue_ownership"]["package_completion_scope"] == "package_only"
    assert record["queue_ownership"]["owns_goal_completion_authority"] is False
    assert record["queue_ownership"]["issues_completion_authority"] is False
    assert result.accepted is False
    assert result.completed is False


def test_goal_queue_runtime_evidence_authority_success_mainline(tmp_path):
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "goal-queue-success", "summary": "create workspace/queue.txt"})

    result = EngineeringGoalLoop(repo_root=tmp_path, repository=repository).run_until_terminal(
        "goal-queue-success", max_cycles=1
    )

    assert result["ok"] is True
    assert result["cycles"][0]["adaptive_decision"] == "complete"
    assert result["goal_completion_authority_result"]["accepted"] is True
