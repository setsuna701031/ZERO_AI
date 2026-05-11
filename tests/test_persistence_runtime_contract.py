from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from core.tasks.scheduler import Scheduler


def _make_scheduler(tmp_path: Path) -> Scheduler:
    return Scheduler(workspace_dir=str(tmp_path / "workspace"))


def _get_repo_task(scheduler: Scheduler, task_id: str) -> Optional[Dict[str, Any]]:
    repo = getattr(scheduler, "task_repo", None)
    assert repo is not None

    for method_name in ("get_task", "get", "load_task", "read_task"):
        method = getattr(repo, method_name, None)
        if callable(method):
            value = method(task_id)
            if isinstance(value, dict):
                return value

    for method_name in ("list_tasks", "all_tasks", "get_all_tasks"):
        method = getattr(repo, method_name, None)
        if not callable(method):
            continue

        tasks = method()

        if isinstance(tasks, dict):
            value = tasks.get(task_id)
            if isinstance(value, dict):
                return value
            tasks = list(tasks.values())

        if isinstance(tasks, list):
            for item in tasks:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("task_id") or item.get("task_name") or item.get("id") or "")
                if item_id == task_id:
                    return item

    db_path = getattr(repo, "db_path", None) or getattr(repo, "path", None)
    if db_path:
        path = Path(str(db_path))
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            candidates = []

            if isinstance(data, dict):
                candidates.append(data.get(task_id))
                for key in ("tasks", "items"):
                    candidates.append(data.get(key))

            for candidate in candidates:
                if isinstance(candidate, dict):
                    value = candidate.get(task_id)
                    if isinstance(value, dict):
                        return value
                    for item in candidate.values():
                        if isinstance(item, dict):
                            item_id = str(item.get("task_id") or item.get("task_name") or item.get("id") or "")
                            if item_id == task_id:
                                return item

                if isinstance(candidate, list):
                    for item in candidate:
                        if isinstance(item, dict):
                            item_id = str(item.get("task_id") or item.get("task_name") or item.get("id") or "")
                            if item_id == task_id:
                                return item

            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        item_id = str(item.get("task_id") or item.get("task_name") or item.get("id") or "")
                        if item_id == task_id:
                            return item

    return None


def test_persist_task_payload_preserves_basic_identity_fields(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task_id = "persist_basic_identity"
    task = {
        "task_id": task_id,
        "task_name": task_id,
        "goal": "persist identity contract",
        "status": "queued",
        "steps": [{"type": "noop"}],
        "execution_log": [{"event": "queued"}],
    }

    scheduler._persist_task_payload(task_id, task)

    repo_task = _get_repo_task(scheduler, task_id)

    assert repo_task is not None
    assert repo_task["task_id"] == task_id
    assert str(repo_task.get("goal") or "") == "persist identity contract"
    assert str(repo_task.get("status") or "") == "queued"


def test_persist_task_payload_writes_runtime_state_file_when_present(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task_id = "persist_runtime_files"

    runtime_state_file = (
        Path(scheduler.workspace_dir)
        / "tasks"
        / task_id
        / "runtime_state.json"
    )
    runtime_state_file.parent.mkdir(parents=True, exist_ok=True)

    task = {
        "task_id": task_id,
        "task_name": task_id,
        "goal": "persist runtime files",
        "status": "running",
        "runtime_state_file": str(runtime_state_file),
        "execution_log": [{"event": "running"}],
        "results": [{"ok": True}],
    }

    scheduler._persist_task_payload(task_id, task)

    repo_task = _get_repo_task(scheduler, task_id)

    assert repo_task is not None
    assert repo_task["task_id"] == task_id
    assert runtime_state_file.exists()

    persisted_runtime_state = json.loads(runtime_state_file.read_text(encoding="utf-8"))
    assert isinstance(persisted_runtime_state, dict)
    assert persisted_runtime_state.get("status") == "running"
    assert str(persisted_runtime_state.get("runtime_state_file") or "") == str(runtime_state_file)


def test_persist_task_payload_refreshes_public_snapshot_when_supported(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task_id = "persist_public_snapshot"

    task = {
        "task_id": task_id,
        "task_name": task_id,
        "goal": "persist public snapshot",
        "status": "finished",
        "steps": [{"type": "write_file"}],
        "results": [{"text": "done"}],
        "step_results": [{"text": "done"}],
        "execution_log": [{"ok": True}],
    }

    scheduler._persist_task_payload(task_id, task)

    repo_task = _get_repo_task(scheduler, task_id)

    assert repo_task is not None
    assert str(repo_task.get("status") or "") == "finished"

    public_snapshot = repo_task.get("public_snapshot")
    if isinstance(public_snapshot, dict):
        assert public_snapshot.get("task_id") == task_id
        assert public_snapshot.get("status") == "finished"


def test_persist_task_payload_handles_missing_optional_fields(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task_id = "persist_missing_optional_fields"

    task = {
        "task_id": task_id,
        "status": "queued",
    }

    scheduler._persist_task_payload(task_id, task)

    repo_task = _get_repo_task(scheduler, task_id)

    assert repo_task is not None
    assert repo_task["task_id"] == task_id
    assert repo_task["status"] == "queued"


def test_persist_task_payload_keeps_available_result_fields(tmp_path: Path) -> None:
    scheduler = _make_scheduler(tmp_path)

    task_id = "persist_results_contract"

    task = {
        "task_id": task_id,
        "task_name": task_id,
        "goal": "persist results",
        "status": "finished",
        "results": [{"text": "result"}],
        "step_results": [{"text": "step"}],
        "execution_log": [{"event": "finished"}],
    }

    scheduler._persist_task_payload(task_id, task)

    repo_task = _get_repo_task(scheduler, task_id)

    assert repo_task is not None
    assert repo_task["task_id"] == task_id
    assert repo_task["status"] == "finished"

    if "results" in repo_task:
        assert repo_task["results"] == [{"text": "result"}]
    if "step_results" in repo_task:
        assert repo_task["step_results"] == [{"text": "step"}]
    if "execution_log" in repo_task:
        assert repo_task["execution_log"] == [{"event": "finished"}]
