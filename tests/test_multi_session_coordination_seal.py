from __future__ import annotations

from pathlib import Path

import pytest

from core.evidence import EvidenceRecord, EvidenceValidator
from core.evidence.evidence_authority import EvidenceAuthority
from core.evidence.evidence_repository import EvidenceRepository
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.runtime.runtime_authority_seal import (
    _RUNTIME_DISPATCHER_ISSUER_TOKEN,
    is_work_package_completion_authority,
    issue_work_package_completion_authority,
)
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.runtime_session_resume import RuntimeSessionResume
from core.runtime.work_package_queue import RuntimePackageQueue
from core.runtime.work_package_queue import RuntimePackageQueueError
from core.tasks.scheduler_core.task_scheduler_queue import ScheduledTask, TaskSchedulerQueue


def _work(session_id: str, *, kind: str = "continuation") -> dict:
    payload = {
        "session_id": session_id,
        "runtime_session_id": session_id,
        "goal_id": "shared-goal",
        "source_goal_id": "source-goal",
        "cycle_index": 1,
        "task_id": "shared-task",
        "evidence_ref": f"evidence-{session_id}",
        "evidence_refs": [f"evidence-{session_id}", f"decision-{session_id}"],
        "decision_evidence_id": f"decision-{session_id}",
        "authority_state": "completion_authority_not_granted",
        "status": "queued",
    }
    if kind == "continuation":
        payload.update(
            {
                "continuation_goal_id": f"continuation-{session_id}",
                "continuation_task_id": "shared-continuation-task",
            }
        )
    if kind == "replan":
        payload["replan_request_id"] = "shared-replan-request"
    return payload


def test_runtime_queue_duplicate_identity_is_scoped_by_session(tmp_path: Path) -> None:
    queue = RuntimePackageQueue(repo_root=tmp_path)
    a = queue.enqueue({"package_id": "package-a", **_work("session-a")})
    b = queue.enqueue({"package_id": "package-b", **_work("session-b")})
    duplicate_a = queue.enqueue({"package_id": "package-a-retry", **_work("session-a")})

    assert len(queue.list_packages()) == 2
    assert a["session_id"] == "session-a"
    assert b["session_id"] == "session-b"
    assert duplicate_a["package_id"] == "package-a"
    assert duplicate_a["queue_admission"]["result"] == "duplicate_idempotent"
    assert duplicate_a["queue_admission"]["matched_identity"]["session_id"] == "session-a"

    with pytest.raises(RuntimePackageQueueError, match="package_id_session_collision"):
        queue.enqueue({"package_id": "package-a", **_work("session-b")})


def test_scheduler_same_task_id_isolated_by_session_and_retry() -> None:
    queue = TaskSchedulerQueue()
    assert queue.enqueue(ScheduledTask(task_id="shared-task", payload=_work("session-a"))) is True
    assert queue.enqueue(ScheduledTask(task_id="shared-task", payload=_work("session-b"))) is True
    assert len(queue) == 2

    assert queue.enqueue(
        ScheduledTask(task_id="shared-task", payload={**_work("session-a"), "attempt": 2}),
        overwrite=True,
    ) is True
    a = queue.get_task("shared-task", session_id="session-a")
    b = queue.get_task("shared-task", session_id="session-b")
    assert a is not None and a.payload["attempt"] == 2
    assert b is not None and "attempt" not in b.payload

    a.status = "blocked"
    queue.upsert_task(a)
    assert queue.get_task("shared-task", session_id="session-a").status == "blocked"
    assert queue.get_task("shared-task", session_id="session-b").status == "queued"


def test_resume_records_are_partitioned_by_session_even_with_same_task_id(tmp_path: Path) -> None:
    store = tmp_path / "resume.json"
    runtime = RuntimeSessionResume(workspace_root=tmp_path, storage_path=store)
    runtime.create_session_record(session_id="session-a", tasks=[_work("session-a")])
    runtime.create_session_record(session_id="session-b", tasks=[_work("session-b", kind="replan")])

    a = runtime.build_resume_plan(session_id="session-a")
    b = runtime.build_resume_plan(session_id="session-b")
    assert a["task_ids"] == b["task_ids"] == ["shared-task"]
    assert a["lineage_by_task_id"]["shared-task"]["session_id"] == "session-a"
    assert b["lineage_by_task_id"]["shared-task"]["session_id"] == "session-b"
    assert "replan_request_id" not in a["lineage_by_task_id"]["shared-task"]
    assert b["lineage_by_task_id"]["shared-task"]["replan_request_id"] == "shared-replan-request"

    runtime.mark_resumed("session-a")
    assert runtime.build_resume_plan(session_id="session-a")["action"] == "idempotent_resume_skip"
    assert runtime.build_resume_plan(session_id="session-b")["task_ids"] == ["shared-task"]


def test_blocked_session_does_not_turn_other_session_into_replan() -> None:
    blocked = RuntimeDispatcher._step_feedback(
        task={"task_id": "shared-task", "session_id": "session-a", "steps": [{}]},
        result={
            "ok": False,
            "status": "failed",
            "error": "policy_denied",
            "next_action": "replan",
        },
        tick=0,
    )
    recoverable = RuntimeDispatcher._step_feedback(
        task={"task_id": "shared-task", "session_id": "session-b", "steps": [{}]},
        result={
            "ok": False,
            "status": "failed",
            "error": "verification_failed",
            "next_action": "replan",
        },
        tick=0,
    )

    assert blocked["next_action"] == "block"
    assert recoverable["next_action"] == "replan"


def _validated_evidence(session_id: str) -> EvidenceRecord:
    return EvidenceValidator().validate(
        EvidenceRecord(
            evidence_id="shared-evidence",
            goal_id="shared-goal",
            subgoal_id="shared-task",
            source="runtime",
            summary="ok",
            timestamp="2026-06-18T00:00:00+00:00",
            metadata={"session_id": session_id},
        )
    )


def test_evidence_registry_and_chains_are_session_isolated(tmp_path: Path) -> None:
    repository = EvidenceRepository(tmp_path, storage_path=tmp_path / "evidence.jsonl")
    authority = EvidenceAuthority(tmp_path, evidence_repository=repository)
    evidence_a = repository.add_record(_validated_evidence("session-a"))
    evidence_b = repository.add_record(_validated_evidence("session-b"))

    chain_a = authority.get_goal_chain("shared-goal", session_id="session-a")
    chain_b = authority.get_goal_chain("shared-goal", session_id="session-b")
    assert chain_a.evidence_ids == ["shared-evidence"]
    assert chain_b.evidence_ids == ["shared-evidence"]
    assert repository.get_record("shared-evidence") is None
    assert repository.get_record("shared-evidence", session_id="session-a") == evidence_a
    assert repository.get_record("shared-evidence", session_id="session-b") == evidence_b


def test_goal_completion_cannot_borrow_evidence_from_another_session() -> None:
    evidence_a = _validated_evidence("session-a")
    evidence_b = _validated_evidence("session-b")

    rejected = GoalCompletionAuthority().complete_goal(
        goal_id="shared-goal",
        session_id="session-a",
        evidence_refs=[evidence_b],
        all_subgoals_completed=True,
    )
    accepted_b = GoalCompletionAuthority().complete_goal(
        goal_id="shared-goal",
        session_id="session-b",
        evidence_refs=[evidence_b],
        all_subgoals_completed=True,
    )

    assert rejected.accepted is False
    assert rejected.reason == "goal_completion_evidence_session_mismatch"
    assert accepted_b.accepted is True
    assert accepted_b.session_id == "session-b"
    assert evidence_a.metadata["session_id"] == "session-a"


def test_package_completion_authority_is_session_scoped() -> None:
    authority_a = issue_work_package_completion_authority(
        _RUNTIME_DISPATCHER_ISSUER_TOKEN,
        package_id="shared-package",
        session_id="session-a",
    )
    assert is_work_package_completion_authority(
        authority_a, package_id="shared-package", session_id="session-a"
    )
    assert not is_work_package_completion_authority(
        authority_a, package_id="shared-package", session_id="session-b"
    )


def test_queue_scheduler_resume_do_not_issue_goal_completion_authority() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "core/runtime/work_package_queue.py",
        "core/runtime/runtime_session_resume.py",
        "core/runtime/persistent_runtime_orchestrator.py",
        "core/tasks/scheduler_core/task_scheduler_queue.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert "issue_goal_completion_authority" not in source
        assert ".complete_goal(" not in source
