from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _workspace_dir() -> str:
    return os.environ.get("ZERO_WORKSPACE", "workspace")


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _tasks_json_path(repo_root: Path) -> Path:
    return repo_root / _workspace_dir() / "tasks.json"


def _read_tasks_index(repo_root: Path) -> List[Dict[str, Any]]:
    path = _tasks_json_path(repo_root)
    if not path.is_file():
        return []

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    if isinstance(data, dict) and isinstance(data.get("tasks"), list):
        return [item for item in data["tasks"] if isinstance(item, dict)]

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    return []


def _task_id(task: Dict[str, Any]) -> str:
    return str(
        task.get("task_id")
        or task.get("task_name")
        or task.get("id")
        or ""
    ).strip()


def _status(task: Dict[str, Any]) -> str:
    return str(task.get("status") or "").strip().lower()


def _goal(task: Dict[str, Any]) -> str:
    return str(
        task.get("goal")
        or task.get("title")
        or task.get("prompt")
        or ""
    ).strip()


def _deps_satisfied(task: Dict[str, Any], by_id: Dict[str, Dict[str, Any]]) -> bool:
    deps = task.get("depends_on")
    if not isinstance(deps, list) or not deps:
        return True

    completed = {"done", "finished", "completed", "success"}
    for dep in deps:
        dep_task = by_id.get(str(dep).strip())
        if not isinstance(dep_task, dict):
            return False
        if _status(dep_task) not in completed:
            return False

    return True


def _ready_tasks(repo_root: Path) -> List[Dict[str, Any]]:
    tasks = _read_tasks_index(repo_root)
    by_id = {_task_id(task): task for task in tasks if _task_id(task)}

    ready_statuses = {"queued", "ready", "retry", "retrying", "running"}
    terminal_statuses = {
        "finished",
        "done",
        "success",
        "completed",
        "failed",
        "error",
        "cancelled",
        "canceled",
    }

    ready: List[Dict[str, Any]] = []
    for task in tasks:
        status = _status(task)
        if not status or status in terminal_statuses:
            continue
        if status not in ready_statuses:
            continue
        if not _deps_satisfied(task, by_id):
            continue
        ready.append(task)

    return ready


def _parse_task_run(argv: List[str]) -> Optional[int]:
    if len(argv) < 2:
        return None

    if str(argv[0]).strip().lower() != "task":
        return None

    if str(argv[1]).strip().lower() != "run":
        return None

    raw_count = str(argv[2]).strip() if len(argv) >= 3 else "1"

    try:
        count = int(raw_count)
    except Exception:
        return None

    if count < 1:
        count = 1

    return count


def _empty_tick_result(tick: int) -> Dict[str, Any]:
    return {
        "ok": True,
        "scheduler_build": "APP_THIN_FAST_EMPTY_QUEUE_V1",
        "tick": tick,
        "rounds_used": 1,
        "max_scheduler_rounds_per_tick": 50,
        "synced_task_ids": [],
        "dispatched_count": 0,
        "executed_count": 0,
        "executed_results": [],
        "snapshot": {
            "queue": {
                "queued_count": 0,
                "total_count": 0,
                "status_counts": {},
                "next_task": None,
            },
            "workers": {
                "max_workers": 1,
                "busy_workers": 0,
                "free_workers": 1,
                "running_count": 0,
                "running_tasks": [],
            },
            "queued_count": 0,
            "total_count": 0,
            "running_count": 0,
            "ready_queue": [],
            "running_tasks": [],
        },
        "fast_cli_path": True,
        "legacy_app_booted": False,
    }


def _empty_manual_ticks(count: int) -> Dict[str, Any]:
    results = [
        {
            "tick_index": i + 1,
            "result": _empty_tick_result(i + 1),
        }
        for i in range(count)
    ]

    return {
        "ok": True,
        "count": count,
        "results": results,
        "mode": "manual_ticks",
        "fast_cli_path": True,
        "legacy_app_booted": False,
    }


def _print_task_table(tasks: List[Dict[str, Any]]) -> None:
    if not tasks:
        print("目前沒有 task。")
        return

    rows: List[Tuple[str, str, str]] = []
    for task in tasks:
        task_id = _task_id(task)
        status = _status(task) or "unknown"
        goal = " ".join(_goal(task).split())
        if len(goal) > 70:
            goal = goal[:67] + "..."
        rows.append((task_id, status, goal))

    task_id_width = max(len("task_id"), min(28, max(len(row[0]) for row in rows)))
    status_width = max(len("status"), min(14, max(len(row[1]) for row in rows)))

    print(f"{'task_id':<{task_id_width}}  {'status':<{status_width}}  goal")
    print("-" * max(80, task_id_width + status_width + 8))
    for task_id, status, goal in rows:
        print(f"{task_id:<{task_id_width}}  {status:<{status_width}}  {goal}")


def _try_handle_fast_task_list(argv: List[str], repo_root: Path) -> bool:
    if len(argv) != 2:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() != "list":
        return False

    _print_task_table(_read_tasks_index(repo_root))
    return True


def _try_handle_fast_task_run(argv: List[str], repo_root: Path) -> bool:
    count = _parse_task_run(argv)
    if count is None:
        return False

    if _ready_tasks(repo_root):
        return False

    _print_json(_empty_manual_ticks(count))
    return True


def try_handle_fast_task_command(argv: List[str], *, repo_root: Path) -> bool:
    clean_argv = [str(item) for item in argv if str(item).strip()]

    if _try_handle_fast_task_run(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_list(clean_argv, repo_root):
        return True

    return False
