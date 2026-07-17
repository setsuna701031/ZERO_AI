from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.tasks.task_store_lock import atomic_write_json, task_store_lock


def workspace_dir() -> str:
    return os.environ.get("ZERO_WORKSPACE", "workspace")


def workspace_root(repo_root: Path) -> Path:
    workspace = Path(workspace_dir())
    if workspace.is_absolute():
        return workspace
    return repo_root / workspace


def read_json_file(path: Path) -> Any:
    with task_store_lock(path).acquire():
        if not path.is_file():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None


def write_json_file(path: Path, data: Any) -> None:
    with task_store_lock(path).acquire():
        atomic_write_json(path, data, default=str)


def tasks_json_path(repo_root: Path) -> Path:
    return workspace_root(repo_root) / "tasks.json"


def scheduler_state_path(repo_root: Path) -> Path:
    return workspace_root(repo_root) / "scheduler_state.json"


def tasks_dir(repo_root: Path) -> Path:
    return workspace_root(repo_root) / "tasks"


def shared_dir(repo_root: Path) -> Path:
    return workspace_root(repo_root) / "shared"


def read_tasks_index(repo_root: Path) -> List[Dict[str, Any]]:
    data = read_json_file(tasks_json_path(repo_root))
    if isinstance(data, dict) and isinstance(data.get("tasks"), list):
        return [item for item in data["tasks"] if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def write_tasks_index(repo_root: Path, tasks: List[Dict[str, Any]]) -> None:
    path = tasks_json_path(repo_root)
    with task_store_lock(path).acquire():
        existing = read_json_file(path)
        if isinstance(existing, dict):
            existing["tasks"] = tasks
            write_json_file(path, existing)
        else:
            write_json_file(path, tasks)


def read_scheduler_state(repo_root: Path) -> Dict[str, Any]:
    data = read_json_file(scheduler_state_path(repo_root))
    return data if isinstance(data, dict) else {}


def task_id(task: Dict[str, Any]) -> str:
    return str(task.get("task_id") or task.get("task_name") or task.get("id") or "").strip()


def task_status(task: Dict[str, Any]) -> str:
    return str(task.get("status") or "").strip().lower()


def task_goal(task: Dict[str, Any]) -> str:
    return str(task.get("goal") or task.get("title") or task.get("prompt") or "").strip()


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def deps_satisfied(task: Dict[str, Any], by_id: Dict[str, Dict[str, Any]]) -> bool:
    deps = task.get("depends_on")
    if not isinstance(deps, list) or not deps:
        return True
    for dep in deps:
        dep_task = by_id.get(str(dep).strip())
        if not isinstance(dep_task, dict):
            return False
        if task_status(dep_task) not in {"done", "finished", "completed", "success"}:
            return False
    return True


def ready_tasks_from_index(repo_root: Path) -> List[Dict[str, Any]]:
    tasks = read_tasks_index(repo_root)
    by_id = {task_id(task): task for task in tasks if task_id(task)}
    ready: List[Dict[str, Any]] = []
    for task in tasks:
        status = task_status(task)
        if not status or status in {"finished", "done", "success", "completed", "failed", "error", "cancelled", "canceled"}:
            continue
        if status not in {"queued", "ready", "retry", "retrying", "running", "replanning"}:
            continue
        if not deps_satisfied(task, by_id):
            continue
        ready.append(task)
    return ready


def extract_state_queue(state: Dict[str, Any]) -> Dict[str, Any]:
    candidates: List[Any] = [state.get("queue"), state.get("snapshot"), state.get("scheduler"), state.get("state")]
    snapshot = state.get("snapshot")
    if isinstance(snapshot, dict):
        candidates.extend([snapshot.get("queue"), snapshot.get("scheduler"), snapshot.get("state")])

    for candidate in candidates:
        if isinstance(candidate, dict):
            queue = candidate.get("queue")
            if isinstance(queue, dict):
                return queue
            if any(key in candidate for key in ("queued_count", "running_count", "ready_queue", "running_tasks", "total_count", "status_counts")):
                return candidate
    return {}


def state_queue_is_empty(state: Dict[str, Any]) -> Optional[bool]:
    if not state:
        return None
    queue = extract_state_queue(state)
    if not queue:
        return None

    ready_queue = queue.get("ready_queue")
    running_tasks = queue.get("running_tasks")
    status_counts = queue.get("status_counts")
    queued_count = as_int(queue.get("queued_count"), 0)
    running_count = as_int(queue.get("running_count"), 0)

    if isinstance(ready_queue, list) and ready_queue:
        return False
    if isinstance(running_tasks, list) and running_tasks:
        return False
    if queued_count > 0 or running_count > 0:
        return False
    if isinstance(status_counts, dict):
        active = sum(as_int(status_counts.get(key), 0) for key in ("queued", "ready", "retry", "retrying", "running", "replanning"))
        if active > 0:
            return False

    if isinstance(ready_queue, list) or isinstance(running_tasks, list) or "queued_count" in queue or "running_count" in queue or isinstance(status_counts, dict):
        return True
    return None


def live_runtime_marker_exists(repo_root: Path) -> bool:
    workspace = workspace_root(repo_root)
    for path in [
        workspace / "scheduler.lock",
        workspace / "scheduler_state.lock",
        workspace / "runtime" / "scheduler.lock",
        workspace / "runtime" / "runtime.lock",
        workspace / "runtime" / "running.lock",
    ]:
        try:
            if path.exists():
                return True
        except Exception:
            continue
    return False


def runtime_queue_empty(repo_root: Path) -> bool:
    state_path = scheduler_state_path(repo_root)
    state_empty = state_queue_is_empty(read_scheduler_state(repo_root))
    if state_empty is not None:
        return bool(state_empty)
    if not state_path.exists():
        return not live_runtime_marker_exists(repo_root)
    return not bool(ready_tasks_from_index(repo_root))
