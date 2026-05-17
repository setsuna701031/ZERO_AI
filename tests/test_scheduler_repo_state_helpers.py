from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.tasks.scheduler_core.repo_state_helpers import (
    compact_runner_result,
    get_task_from_repo,
    list_repo_tasks,
    mark_repo_task_with_adapter,
)


class ListOnlyRepo:
    def __init__(self, tasks: List[Dict[str, Any]]) -> None:
        self.tasks = tasks

    def list_tasks(self) -> List[Dict[str, Any]]:
        return self.tasks


class GetRepo:
    def __init__(self, task: Dict[str, Any]) -> None:
        self.task = task

    def get_task(self, task_id: str) -> Dict[str, Any]:
        return self.task if task_id == self.task.get("task_id") else {}


class DummyScheduler:
    def __init__(self, repo: Any) -> None:
        self.task_repo = repo
        self.hydrated: List[str] = []

    def _hydrate_task_from_workspace(self, task: Dict[str, Any]) -> Dict[str, Any]:
        hydrated = copy.deepcopy(task)
        hydrated["hydrated"] = True
        self.hydrated.append(str(task.get("task_id") or task.get("task_name") or ""))
        return hydrated

    def _extract_task_id(self, task: Dict[str, Any]) -> str:
        return str(task.get("task_id") or task.get("task_name") or task.get("id") or "").strip()


class DummyWorkerPool:
    def __init__(self) -> None:
        self.released: List[str] = []

    def release_by_task(self, task_id: str) -> None:
        self.released.append(task_id)


class MarkScheduler:
    SCHEDULER_BUILD = "test-build"
    TERMINAL_STATUSES = {"finished", "failed", "blocked"}

    def __init__(self, task: Dict[str, Any]) -> None:
        self.task = task
        self.current_tick = 7
        self.worker_pool = DummyWorkerPool()
        self.persisted: List[Dict[str, Any]] = []
        self.unblocked = 0

    def _get_task_from_repo(self, task_id: str) -> Dict[str, Any]:
        return self.task if task_id == self.task.get("task_id") else {}

    def _append_history(self, history: Any, status: str) -> List[str]:
        items = list(history) if isinstance(history, list) else []
        items.append(status)
        return items

    def _persist_task_payload(self, task_id: str, task: Dict[str, Any]) -> None:
        self.persisted.append(copy.deepcopy(task))

    def _unblock_tasks_if_dependencies_done(self) -> None:
        self.unblocked += 1


def test_list_repo_tasks_filters_non_dicts_and_hydrates() -> None:
    scheduler = DummyScheduler(ListOnlyRepo([{"task_id": "a"}, "bad", {"task_name": "b"}]))

    tasks = list_repo_tasks(scheduler)

    assert tasks == [
        {"task_id": "a", "hydrated": True},
        {"task_name": "b", "hydrated": True},
    ]
    assert scheduler.hydrated == ["a", "b"]


def test_get_task_from_repo_uses_direct_getter_before_list_scan() -> None:
    scheduler = DummyScheduler(GetRepo({"task_id": "direct", "status": "queued"}))

    task = get_task_from_repo(scheduler, " direct ")

    assert task == {"task_id": "direct", "status": "queued", "hydrated": True}


def test_get_task_from_repo_falls_back_to_list_scan_by_task_name() -> None:
    scheduler = DummyScheduler(ListOnlyRepo([{"task_name": "fallback", "status": "running"}]))

    task = get_task_from_repo(scheduler, "fallback")

    assert task == {"task_name": "fallback", "status": "running", "hydrated": True}


def test_get_task_from_repo_returns_none_for_missing_or_empty_task_id() -> None:
    scheduler = DummyScheduler(ListOnlyRepo([{"task_id": "a"}]))

    assert get_task_from_repo(scheduler, "") is None
    assert get_task_from_repo(scheduler, "missing") is None


def test_compact_runner_result_keeps_simple_terminal_shape() -> None:
    result = {
        "ok": True,
        "action": "simple_task_finished",
        "task_id": "task_1",
        "status": "finished",
        "step_count": 2,
        "steps_total": 2,
        "step_results": [{"large": "payload"}],
        "orchestration_summary": {"chain": "ok"},
    }

    compact = compact_runner_result(result)

    assert compact == {
        "ok": True,
        "action": "simple_task_finished",
        "task_id": "task_1",
        "status": "finished",
        "step_count": 2,
        "steps_total": 2,
        "orchestration_summary": {"chain": "ok"},
    }
    assert "step_results" not in compact


def test_compact_runner_result_handles_nested_multi_code_edit_without_mutating() -> None:
    result = {
        "task_id": "outer",
        "status": "running",
        "step_count": 3,
        "steps_total": 5,
        "last_step_result": {
            "task_id": "inner",
            "status": "failed",
            "result": {
                "ok": False,
                "action": "multi_code_edit_failed",
                "atomic": True,
                "changed_files": ["a.py"],
                "error": "boom",
            },
        },
    }
    original = copy.deepcopy(result)

    compact = compact_runner_result(result)

    assert compact == {
        "ok": False,
        "action": "multi_code_edit_failed",
        "task_id": "inner",
        "status": "failed",
        "atomic": True,
        "rollback": True,
        "changed_files": ["a.py"],
        "edit_count": 0,
        "failed_reason": "boom",
        "step_count": 3,
        "steps_total": 5,
    }
    assert result == original


def test_mark_repo_task_adapter_invokes_finished_callback() -> None:
    calls: List[Dict[str, Any]] = []
    scheduler = MarkScheduler({"task_id": "task-1", "status": "running"})
    scheduler.repo_task_mark_callbacks = {
        "mark_finished": lambda **kwargs: calls.append(kwargs),
    }

    mark_repo_task_with_adapter(
        scheduler=scheduler,
        operation="finished",
        task_id="task-1",
        result="done",
    )

    assert calls == [
        {
            "scheduler": scheduler,
            "task_id": "task-1",
            "result": "done",
        }
    ]
    assert scheduler.persisted == []


def test_mark_repo_task_adapter_invokes_failed_callback() -> None:
    calls: List[Dict[str, Any]] = []
    scheduler = MarkScheduler({"task_id": "task-1", "status": "running"})
    scheduler.repo_task_mark_callbacks = {
        "mark_failed": lambda **kwargs: calls.append(kwargs),
    }

    mark_repo_task_with_adapter(
        scheduler=scheduler,
        operation="failed",
        task_id="task-1",
        error="boom",
    )

    assert calls == [
        {
            "scheduler": scheduler,
            "task_id": "task-1",
            "error": "boom",
        }
    ]
    assert scheduler.persisted == []


def test_mark_repo_task_adapter_invokes_queued_callback() -> None:
    calls: List[Dict[str, Any]] = []
    scheduler = MarkScheduler({"task_id": "task-1", "status": "running"})
    scheduler.repo_task_mark_callbacks = {
        "mark_queued": lambda **kwargs: calls.append(kwargs),
    }

    mark_repo_task_with_adapter(
        scheduler=scheduler,
        operation="queued",
        task_id="task-1",
        error="retry later",
    )

    assert calls == [
        {
            "scheduler": scheduler,
            "task_id": "task-1",
            "error": "retry later",
        }
    ]
    assert scheduler.persisted == []


def test_mark_repo_task_adapter_preserves_finished_contract_without_callback() -> None:
    scheduler = MarkScheduler({"task_id": "task-1", "status": "running", "history": []})

    mark_repo_task_with_adapter(
        scheduler=scheduler,
        operation="finished",
        task_id="task-1",
        result="done",
    )

    assert scheduler.task["status"] == "finished"
    assert scheduler.task["final_answer"] == "done"
    assert scheduler.task["finished_tick"] == 7
    assert scheduler.task["history"] == ["finished"]
    assert scheduler.worker_pool.released == ["task-1"]
    assert scheduler.unblocked == 1
    assert scheduler.persisted[-1]["status"] == "finished"


def test_mark_repo_task_adapter_preserves_failed_contract_without_callback() -> None:
    scheduler = MarkScheduler({"task_id": "task-1", "status": "running", "history": []})

    mark_repo_task_with_adapter(
        scheduler=scheduler,
        operation="failed",
        task_id="task-1",
        error="boom",
    )

    assert scheduler.task["status"] == "failed"
    assert scheduler.task["last_error"] == "boom"
    assert scheduler.task["failure_message"] == "boom"
    assert scheduler.task["last_failure_tick"] == 7
    assert scheduler.task["history"] == ["failed"]
    assert scheduler.worker_pool.released == ["task-1"]
    assert scheduler.persisted[-1]["status"] == "failed"


def test_mark_repo_task_adapter_preserves_queued_contract_without_callback() -> None:
    scheduler = MarkScheduler({"task_id": "task-1", "status": "running", "history": []})

    mark_repo_task_with_adapter(
        scheduler=scheduler,
        operation="queued",
        task_id="task-1",
        error="retry later",
    )

    assert scheduler.task["status"] == "queued"
    assert scheduler.task["last_error"] == "retry later"
    assert scheduler.task["failure_message"] == "retry later"
    assert scheduler.task["history"] == ["queued"]
    assert scheduler.persisted[-1]["status"] == "queued"
