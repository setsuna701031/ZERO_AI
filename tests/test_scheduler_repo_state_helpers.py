from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.tasks.scheduler_core.repo_state_helpers import (
    compact_runner_result,
    get_task_from_repo,
    list_repo_tasks,
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
