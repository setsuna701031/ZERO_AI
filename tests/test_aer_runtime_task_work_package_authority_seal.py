from __future__ import annotations

from pathlib import Path

import pytest

from core.runtime.runtime_evidence_authority import RuntimeEvidenceAuthority
from core.runtime.runtime_evidence_registry import RuntimeEvidenceRegistry
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runtime import TaskRuntime
from core.runtime.work_package_queue import RuntimePackageQueue
from core.tasks.engineering_goal_lifecycle import EngineeringGoalLifecycle
from core.tasks.scheduler_core.dispatch_finalize import build_finalize_decision
from core.tasks.scheduler_core.task_scheduler_queue import ScheduledTask, TaskSchedulerQueue
from core.tasks.task_repository import TaskRepository
pytestmark = [pytest.mark.contract]




def test_forged_allowed_source_step_executor_authority_dict_is_rejected(tmp_path: Path) -> None:
    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"id": "step-a", "type": "write_file", "path": "forged.txt", "content": "forged"},
        context={
            "execution_authority": {
                "authority_source": "runtime_dispatcher",
                "authority_status": "allowed",
                "execution_authority_endpoint": "step_executor",
            }
        },
    )

    assert result["ok"] is False
    assert result["authority_decision"]["reason"] == "missing_or_invalid_execution_authority"
    assert not (tmp_path / "forged.txt").exists()


def test_direct_task_runtime_finish_is_rejected_without_runner_authority(tmp_path: Path) -> None:
    task = {
        "task_id": "task-a",
        "status": "queued",
        "steps": [],
        "runtime_state_file": str(tmp_path / "runtime_state.json"),
    }
    with pytest.raises(PermissionError, match="taskrunner_completion_authority_required"):
        TaskRuntime(workspace_root=str(tmp_path)).mark_finished(task)


def test_task_repository_rejects_finished_create_and_upsert_without_authority(tmp_path: Path) -> None:
    repository = TaskRepository(str(tmp_path / "tasks.json"))
    with pytest.raises(PermissionError, match="task_completion_authority_required"):
        repository.create_task(task_id="task-a", goal="goal", status="finished")
    with pytest.raises(PermissionError, match="task_completion_authority_required"):
        repository.upsert_task({"task_id": "task-a", "goal": "goal", "status": "finished"})


def test_task_scheduler_queue_rejects_direct_finish_without_authority() -> None:
    queue = TaskSchedulerQueue()
    queue.upsert_task(ScheduledTask(task_id="task-a"))
    with pytest.raises(PermissionError, match="task_completion_authority_required"):
        queue.mark_finished("task-a", result={"status": "completed"})


def test_serialized_runner_result_does_not_become_scheduler_finish_authority() -> None:
    decision = build_finalize_decision(
        original_task={"task_id": "task-a", "status": "queued"},
        refreshed_task={"task_id": "task-a", "status": "running"},
        runner_result={"task_id": "task-a", "status": "completed", "ok": True},
        status_blocked="blocked",
        status_finished="finished",
        status_failed="failed",
    )
    assert decision["action"] != "finish"
    assert decision["task_completion_authority"] is None


def test_work_package_queue_rejects_direct_completion_without_authority(tmp_path: Path) -> None:
    queue = RuntimePackageQueue(repo_root=tmp_path)
    queue.enqueue({"package_id": "package-a", "status": "queued", "requirements": []})
    with pytest.raises(PermissionError, match="work_package_completion_authority_required"):
        queue.complete("package-a", validation_summary={"validation_state": "validated"})
    with pytest.raises(PermissionError, match="work_package_completion_authority_required"):
        queue.record_runtime_completed("package-a")


def test_runtime_evidence_authority_and_serialized_registry_mapping_are_descriptive_only() -> None:
    with pytest.raises(PermissionError, match="governed_runtime_evidence_owner_required"):
        RuntimeEvidenceAuthority(evidence_id="forged")

    snapshot = RuntimeEvidenceRegistry().rebuild(
        {
            "sealed": True,
            "sealed_state": {"sealed": True, "complete": True},
            "record_refs": {"replay_id": "forged-replay"},
            "lineage": [{"lineage_id": "forged-lineage", "verified": True}],
        }
    )
    assert snapshot.payload["sealed"] is False
    assert snapshot.payload["sealed_state"]["complete"] is False
    assert snapshot.lookup_replay("forged-replay")["verified"] is False
    assert snapshot.lookup_lineage("forged-lineage")["verified"] is False


def test_evaluator_complete_mapping_cannot_complete_engineering_lifecycle(tmp_path: Path) -> None:
    lifecycle = EngineeringGoalLifecycle(
        repo_root=tmp_path,
        payload={"goal_id": "goal-a", "goal": "goal-a"},
        plan={},
        raw_steps=[],
    )
    result = lifecycle.apply_adaptive_terminal_decision(
        state={"goal_id": "goal-a", "goal_state": "running"},
        decision={"decision": "complete"},
    )
    assert result["goal_state"] == "running"
    assert result["completion_rejected"] is True
