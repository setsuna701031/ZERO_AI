from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.tasks.scheduler_core.repo_runtime_sync import (
    _save_runtime_state_from_merged,
    _select_effective_task_payload,
    _sync_loop_fields_into_merged,
    _sync_review_fields_into_merged,
    sync_runtime_back_to_repo,
)


class Runtime:
    def __init__(self, state: Dict[str, Any] | None = None) -> None:
        self.state = state
        self.saved: List[Dict[str, Any]] = []

    def load_runtime_state(self, task: Dict[str, Any]) -> Dict[str, Any] | None:
        return copy.deepcopy(self.state)

    def save_runtime_state(self, task: Dict[str, Any], state: Dict[str, Any]) -> None:
        self.saved.append({"task": copy.deepcopy(task), "state": copy.deepcopy(state)})


class Scheduler:
    SCHEDULER_BUILD = "test-build"
    STATUS_BLOCKED = "blocked"
    STATUS_FAILED = "failed"
    STATUS_FINISHED = "finished"
    STATUS_QUEUED = "queued"
    TERMINAL_STATUSES = {"finished", "failed"}

    def __init__(self, task: Dict[str, Any], runtime: Runtime | None = None) -> None:
        self.task = task
        self.task_runtime = runtime
        self.tasks_root = "tasks-root"
        self.workspace_root = "workspace-root"
        self.shared_dir = "shared-dir"
        self.persisted: List[Dict[str, Any]] = []

    def _get_task_from_repo(self, task_id: str) -> Dict[str, Any]:
        return copy.deepcopy(self.task) if task_id == self.task.get("task_id") else {}

    def _hydrate_task_from_workspace(self, task: Dict[str, Any]) -> Dict[str, Any]:
        hydrated = copy.deepcopy(task)
        hydrated["hydrated"] = True
        return hydrated

    def _backfill_replan_decision_fields(self, task: Dict[str, Any], replan_result: Any = None) -> Dict[str, Any]:
        return task

    def _infer_completion_fields(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return task

    def _clear_stale_replan_fields(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return task

    def _refresh_task_public_fields(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return task

    def _persist_task_payload(
        self,
        task_id: str,
        task: Dict[str, Any],
        completion_authority: Any = None,
    ) -> None:
        self.persisted.append(copy.deepcopy(task))


def test_select_effective_task_payload_prefers_runner_task_without_mutating() -> None:
    task = {"task_id": "task-1", "status": "running"}
    runner_result = {"task": {"status": "paused", "last_decision": "wait"}}

    effective = _select_effective_task_payload(task, runner_result)

    assert effective == {"task_id": "task-1", "status": "paused", "last_decision": "wait"}
    assert task == {"task_id": "task-1", "status": "running"}


def test_sync_loop_and_review_fields_copy_values() -> None:
    merged: Dict[str, Any] = {}
    source = {
        "last_observation": {"x": 1},
        "last_decision": "continue",
        "review_payload": {"review": True},
        "requires_review": True,
    }

    _sync_loop_fields_into_merged(merged, source)
    _sync_review_fields_into_merged(merged, source)
    source["last_observation"]["x"] = 2
    source["review_payload"]["review"] = False

    assert merged["last_observation"] == {"x": 1}
    assert merged["review_payload"] == {"review": True}
    assert merged["last_decision"] == "continue"
    assert merged["requires_review"] is True


def test_save_runtime_state_merges_loaded_state() -> None:
    runtime = Runtime({"existing": True, "status": "old"})
    scheduler = Scheduler({"task_id": "task-1"}, runtime)

    _save_runtime_state_from_merged(scheduler, {"task_id": "task-1", "status": "running"})

    assert runtime.saved[-1]["state"] == {
        "existing": True,
        "task_id": "task-1",
        "status": "running",
    }


def test_sync_runtime_back_to_repo_persists_merged_runtime_payload() -> None:
    runtime = Runtime({"priority": 3, "status": "paused"})
    scheduler = Scheduler(
        {"task_id": "task-1", "status": "running", "steps": [{"kind": "one"}]},
        runtime,
    )

    sync_runtime_back_to_repo(
        scheduler,
        {"task_id": "task-1", "last_decision": "continue"},
        {"status": "paused", "final_answer": "not done", "review_status": "pending"},
    )

    persisted = scheduler.persisted[-1]
    assert persisted["status"] == "paused"
    assert persisted["priority"] == 3
    assert persisted["last_decision"] == "continue"
    assert persisted["review_status"] == "pending"
    assert persisted["adapter_payload"]["runtime_mode"] == "repo_state"
    assert runtime.saved
