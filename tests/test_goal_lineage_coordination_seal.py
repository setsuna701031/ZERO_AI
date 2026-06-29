from __future__ import annotations

import copy

from core.adaptive.continuation_coordinator import ContinuationCoordinator
from core.adaptive.continuation_runtime import ContinuationRuntime
from core.adaptive.replan_coordinator import ReplanCoordinator
from core.adaptive.replan_runtime import ReplanRuntime
from core.evidence import EvidenceRecord, EvidenceValidator
from core.evidence.evidence_authority import EvidenceAuthority
from core.evidence.evidence_repository import EvidenceRepository
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.goals.goal_lineage_contract import (

    attach_goal_lineage,
    canonical_work_identity,
    extract_goal_lineage,
)
from core.runtime.runtime_session_resume import RuntimeSessionResume
from core.runtime.persistent_runtime_orchestrator import PersistentRuntimeOrchestrator
from core.runtime.work_package_queue import RuntimePackageQueue
from core.tasks.scheduler_core.task_scheduler_queue import ScheduledTask, TaskSchedulerQueue
import pytest

pytestmark = [pytest.mark.contract]



def _lineage(root: str, *, session: str, branch_type: str = "root", branch_id: str | None = None, goal: str | None = None):
    return extract_goal_lineage(
        {
            "root_goal_id": root,
            "source_goal_id": root,
            "goal_id": goal or root,
            "branch_type": branch_type,
            "branch_id": branch_id or root,
            "session_id": session,
            "runtime_session_id": f"runtime-{session}",
        },
        require_complete=True,
    )


class _GoalRepository:
    def __init__(self):
        self.goals = {}

    def save_goal(self, goal):
        self.goals[goal["goal_id"]] = copy.deepcopy(goal)
        return copy.deepcopy(goal)

    def load_goal(self, goal_id):
        return copy.deepcopy(self.goals.get(goal_id))


def test_root_children_keep_canonical_goal_lineage_contract():
    repository = _GoalRepository()
    root = _lineage("goal-a", session="session-a")
    cycle = attach_goal_lineage({"goal_id": "goal-a", "cycle_index": 0}, root)
    coordinator = ContinuationCoordinator(repository=repository)

    continuation_1, runtime = coordinator.create_work_item(
        runtime=ContinuationRuntime.start("goal-a", max_continuations=2),
        cycle=cycle,
        continuation_plan={"next_runtime_request": {"payload": {"goal": "continue"}}},
    )
    cycle_2 = attach_goal_lineage({"goal_id": continuation_1["goal_id"], "cycle_index": 1}, continuation_1)
    continuation_2, _ = coordinator.create_work_item(
        runtime=runtime,
        cycle=cycle_2,
        goal_id=continuation_1["goal_id"],
        cycle_index=1,
        continuation_plan={"next_runtime_request": {"payload": {"goal": "continue again"}}},
    )
    replan, _ = ReplanCoordinator().create_replan_record(
        runtime=ReplanRuntime.start(max_replans=1),
        cycle=cycle,
        replan_request={"request_id": "replan-1", "reason": "verification_failed"},
    )

    for child in (continuation_1, continuation_2, replan):
        lineage = extract_goal_lineage(child, require_complete=True)
        assert lineage["root_goal_id"] == "goal-a"
        assert lineage["session_id"] == "session-a"
        assert lineage["runtime_session_id"] == "runtime-session-a"
        assert lineage["goal_lineage_id"] == root["goal_lineage_id"]
    assert continuation_1["source_goal_id"] == "goal-a"
    assert continuation_2["source_goal_id"] == continuation_1["goal_id"]
    assert replan["branch_type"] == "replan"
    assert replan["branch_id"] == "replan-1"


def test_duplicate_gate_uses_root_session_and_exact_child_identity(tmp_path):
    queue = RuntimePackageQueue(repo_root=tmp_path)
    a = attach_goal_lineage({"package_id": "a", "task_id": "shared"}, _lineage("goal-a", session="s", branch_type="continuation", branch_id="continuation-1", goal="child"))
    same = attach_goal_lineage({"package_id": "a-retry", "task_id": "renamed"}, a)
    other_root = attach_goal_lineage({"package_id": "b", "task_id": "shared"}, _lineage("goal-b", session="s", branch_type="continuation", branch_id="continuation-1", goal="child"))
    other_session = attach_goal_lineage({"package_id": "c", "task_id": "shared"}, _lineage("goal-a", session="other", branch_type="continuation", branch_id="continuation-1", goal="child"))

    queue.enqueue(a)
    assert queue.enqueue(same)["package_id"] == "a"
    queue.enqueue(other_root)
    queue.enqueue(other_session)
    assert len(queue.list_packages()) == 3
    assert canonical_work_identity(a) != canonical_work_identity(other_root)
    assert canonical_work_identity(a) != canonical_work_identity(other_session)


def test_retry_fail_finish_are_branch_isolated():
    queue = TaskSchedulerQueue()
    continuation = attach_goal_lineage({"task_id": "shared", "attempt": 1}, _lineage("goal-a", session="s", branch_type="continuation", branch_id="c1", goal="child-c1"))
    replan = attach_goal_lineage({"task_id": "shared"}, _lineage("goal-a", session="s", branch_type="replan", branch_id="r1", goal="goal-a"))
    queue.enqueue(ScheduledTask(task_id="shared", payload=continuation))
    queue.enqueue(ScheduledTask(task_id="shared", payload=replan))
    queue.enqueue(ScheduledTask(task_id="shared", payload={**continuation, "attempt": 2}), overwrite=True)

    c1 = queue.get_task("shared", session_id="s", goal_lineage_id=continuation["goal_lineage_id"], branch_id="c1")
    r1 = queue.get_task("shared", session_id="s", goal_lineage_id=replan["goal_lineage_id"], branch_id="r1")
    assert c1 is not None and c1.payload["attempt"] == 2
    assert r1 is not None and "attempt" not in r1.payload
    c1.status = "finished"
    queue.upsert_task(c1)
    r1.status = "failed"
    queue.upsert_task(r1)
    assert queue.get_task("shared", session_id="s", goal_lineage_id=continuation["goal_lineage_id"], branch_id="c1").status == "finished"
    assert queue.get_task("shared", session_id="s", goal_lineage_id=replan["goal_lineage_id"], branch_id="r1").status == "failed"


def _validated(root: str, session: str, evidence_id: str):
    lineage = _lineage(root, session=session)
    return EvidenceValidator().validate(
        EvidenceRecord(
            evidence_id=evidence_id,
            goal_id=root,
            subgoal_id=None,
            source="runtime",
            summary="ok",
            timestamp="2026-06-18T00:00:00+00:00",
            metadata={**lineage, "goal_lineage": lineage},
        )
    )


def test_evidence_authority_and_completion_reject_wrong_goal_lineage(tmp_path):
    repository = EvidenceRepository(tmp_path, storage_path=tmp_path / "evidence.jsonl")
    evidence_a = repository.add_record(_validated("goal-a", "s-a", "same-evidence"))
    evidence_b = repository.add_record(_validated("goal-b", "s-b", "same-evidence"))
    lineage_a = _lineage("goal-a", session="s-a")

    chain = EvidenceAuthority(tmp_path, evidence_repository=repository).get_goal_chain(
        "goal-a",
        session_id="s-a",
        goal_lineage_id=lineage_a["goal_lineage_id"],
        root_goal_id="goal-a",
    )
    rejected = GoalCompletionAuthority().complete_goal(
        goal_id="goal-a",
        evidence_refs=[evidence_b],
        all_subgoals_completed=True,
        goal_lineage=lineage_a,
    )
    accepted = GoalCompletionAuthority().complete_goal(
        goal_id="goal-a",
        evidence_refs=[evidence_a],
        all_subgoals_completed=True,
        goal_lineage=lineage_a,
    )

    assert chain.evidence_ids == ["same-evidence"]
    assert rejected.reason == "goal_completion_evidence_lineage_mismatch"
    assert rejected.completed is False
    assert accepted.completed is True
    assert accepted.goal_lineage["goal_lineage_id"] == lineage_a["goal_lineage_id"]


def test_persistent_restore_partitions_root_lineages_and_second_resume_skips(tmp_path):
    store = tmp_path / "resume.json"
    runtime = RuntimeSessionResume(workspace_root=tmp_path, storage_path=store)
    task_a = attach_goal_lineage({"task_id": "shared", "status": "running"}, _lineage("goal-a", session="s-a", branch_type="continuation", branch_id="c1", goal="child-a"))
    task_b = attach_goal_lineage({"task_id": "shared", "status": "running"}, _lineage("goal-b", session="s-b", branch_type="replan", branch_id="r1", goal="goal-b"))
    runtime.create_session_record(session_id="s-a", tasks=[task_a])
    runtime.create_session_record(session_id="s-b", tasks=[task_b])

    plan_a = runtime.build_resume_plan(session_id="s-a")
    before_b = runtime.build_resume_plan(session_id="s-b")
    runtime.mark_resumed("s-a")
    second_a = runtime.build_resume_plan(session_id="s-a")
    after_b = runtime.build_resume_plan(session_id="s-b")

    assert plan_a["lineage_by_task_id"]["shared"]["root_goal_id"] == "goal-a"
    assert {key: value for key, value in before_b.items() if key != "created_at"} == {
        key: value for key, value in after_b.items() if key != "created_at"
    }
    assert second_a["action"] == "idempotent_resume_skip"
    assert after_b["lineage_by_task_id"]["shared"]["root_goal_id"] == "goal-b"


def test_persistent_runtime_orchestrator_requeues_only_requested_lineage(tmp_path):
    class Repository:
        def __init__(self, tasks):
            self.tasks = list(tasks)

        def list_tasks(self):
            return copy.deepcopy(self.tasks)

        def save_task(self, task):
            identity = canonical_work_identity(task)
            self.tasks = [item for item in self.tasks if canonical_work_identity(item) != identity]
            self.tasks.append(copy.deepcopy(task))
            return task

    class Scheduler:
        def __init__(self):
            self.calls = []

        def submit_existing_task(self, task_id, *, goal_lineage):
            self.calls.append((task_id, copy.deepcopy(goal_lineage)))
            return {"ok": True, "task_id": task_id}

    store = tmp_path / "resume.json"
    task_a = attach_goal_lineage({"task_id": "shared", "status": "running"}, _lineage("goal-a", session="s-a", branch_type="continuation", branch_id="c1", goal="child-a"))
    task_b = attach_goal_lineage({"task_id": "shared", "status": "running"}, _lineage("goal-b", session="s-b", branch_type="replan", branch_id="r1", goal="goal-b"))
    resume = RuntimeSessionResume(workspace_root=tmp_path, storage_path=store)
    resume.create_session_record(session_id="s-a", tasks=[task_a])
    resume.create_session_record(session_id="s-b", tasks=[task_b])
    scheduler = Scheduler()
    orchestrator = PersistentRuntimeOrchestrator(
        repo_root=tmp_path,
        workspace_dir=tmp_path / "workspace",
        resume_store_path=store,
        auto_create_resume_record=False,
    )

    result = orchestrator.resume_last_session(
        task_repository=Repository([task_a, task_b]),
        scheduler=scheduler,
        session_id="s-a",
    )

    assert result["requeued_task_ids"] == ["shared"]
    assert len(scheduler.calls) == 1
    assert scheduler.calls[0][1]["root_goal_id"] == "goal-a"
    assert RuntimeSessionResume(workspace_root=tmp_path, storage_path=store).build_resume_plan(session_id="s-b")["lineage_by_task_id"]["shared"]["root_goal_id"] == "goal-b"
