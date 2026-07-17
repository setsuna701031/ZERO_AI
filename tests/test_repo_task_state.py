from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.runtime.runtime_authority_seal import (
    _RUNTIME_DISPATCHER_ISSUER_TOKEN,
    _TASK_RUNNER_ISSUER_TOKEN,
    delegate_taskrunner_execution_capability,
    issue_dispatch_execution_capability,
    issue_task_completion_authority,
    issue_terminal_execution_evidence,
)
from core.tasks.scheduler_core.repo_task_state import (
    mark_repo_task_failed,
    mark_repo_task_finished,
    mark_repo_task_queued,
    mark_repo_task_with_adapter,
)


def _completion_authority(task_id: str):
    package_id = "repo-task-state-package"
    session_id = "repo-task-state-session"
    step_id = f"{task_id}:terminal"
    dispatch = issue_dispatch_execution_capability(
        _RUNTIME_DISPATCHER_ISSUER_TOKEN,
        task_id=task_id,
        package_id=package_id,
        session_id=session_id,
    )
    delegated = delegate_taskrunner_execution_capability(
        _TASK_RUNNER_ISSUER_TOKEN,
        dispatch,
        task_id=task_id,
        step_id=step_id,
    )
    evidence = issue_terminal_execution_evidence(
        _TASK_RUNNER_ISSUER_TOKEN,
        delegated,
        task_id=task_id,
        package_id=package_id,
        session_id=session_id,
        step_id=step_id,
    )
    return issue_task_completion_authority(
        _TASK_RUNNER_ISSUER_TOKEN,
        task_id=task_id,
        package_id=package_id,
        session_id=session_id,
        evidence=evidence,
    )


class WorkerPool:
    def __init__(self) -> None:
        self.released: List[str] = []

    def release_by_task(self, task_id: str) -> None:
        self.released.append(task_id)


class Scheduler:
    SCHEDULER_BUILD = "test-build"
    TERMINAL_STATUSES = {"finished", "failed"}

    def __init__(self, task: Dict[str, Any]) -> None:
        self.task = task
        self.current_tick = 11
        self.worker_pool = WorkerPool()
        self.persisted: List[Dict[str, Any]] = []
        self.unblocked = 0

    def _get_task_from_repo(self, task_id: str) -> Dict[str, Any]:
        return self.task if task_id == self.task.get("task_id") else {}

    def _append_history(self, history: Any, status: str) -> List[str]:
        items = list(history) if isinstance(history, list) else []
        items.append(status)
        return items

    def _persist_task_payload(
        self,
        task_id: str,
        task: Dict[str, Any],
        completion_authority: Any = None,
    ) -> None:
        self.persisted.append(copy.deepcopy(task))

    def _unblock_tasks_if_dependencies_done(self) -> None:
        self.unblocked += 1


def test_mark_repo_task_finished_updates_terminal_fields() -> None:
    scheduler = Scheduler({"task_id": "task-1", "status": "running", "history": []})

    mark_repo_task_finished(
        scheduler,
        "task-1",
        result="done",
        completion_authority=_completion_authority("task-1"),
    )

    assert scheduler.task["status"] == "finished"
    assert scheduler.task["final_answer"] == "done"
    assert scheduler.task["finished_tick"] == 11
    assert scheduler.worker_pool.released == ["task-1"]
    assert scheduler.unblocked == 1


def test_mark_repo_task_failed_attaches_observability_event() -> None:
    scheduler = Scheduler({"task_id": "task-1", "status": "running", "history": []})

    mark_repo_task_failed(scheduler, "task-1", error="boom")

    assert scheduler.task["status"] == "failed"
    assert scheduler.task["last_error"] == "boom"
    assert scheduler.task["failure_message"] == "boom"
    assert scheduler.task["observability_event"]["event_type"] == "repo_task_failed"
    assert scheduler.worker_pool.released == ["task-1"]


def test_mark_repo_task_queued_skips_terminal_tasks() -> None:
    scheduler = Scheduler({"task_id": "task-1", "status": "finished", "history": []})

    mark_repo_task_queued(scheduler, "task-1", error="retry")

    assert scheduler.persisted == []
    assert scheduler.task["status"] == "finished"


def test_mark_repo_task_with_adapter_uses_callback() -> None:
    scheduler = Scheduler({"task_id": "task-1", "status": "running"})
    calls: List[Dict[str, Any]] = []
    scheduler.repo_task_mark_adapter = {"mark_failed": lambda **kwargs: calls.append(kwargs)}

    mark_repo_task_with_adapter(scheduler, "failed", "task-1", error="boom")

    assert calls == [{"scheduler": scheduler, "task_id": "task-1", "error": "boom"}]
    assert scheduler.persisted == []
