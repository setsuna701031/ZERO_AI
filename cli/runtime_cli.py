from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List


def _workspace_dir() -> str:
    return os.environ.get("ZERO_WORKSPACE", "workspace")


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _workspace_root(repo_root: Path) -> Path:
    workspace = Path(_workspace_dir())
    if workspace.is_absolute():
        return workspace
    return repo_root / workspace


def _tasks_json_path(repo_root: Path) -> Path:
    return _workspace_root(repo_root) / "tasks.json"


def _scheduler_state_path(repo_root: Path) -> Path:
    return _workspace_root(repo_root) / "scheduler_state.json"


def _read_json_file(path: Path) -> Any:
    if not path.is_file():
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _read_tasks_index(repo_root: Path) -> List[Dict[str, Any]]:
    data = _read_json_file(_tasks_json_path(repo_root))

    if isinstance(data, dict) and isinstance(data.get("tasks"), list):
        return [item for item in data["tasks"] if isinstance(item, dict)]

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    return []


def _save_tasks_index(
    repo_root: Path,
    tasks: List[Dict[str, Any]],
) -> None:
    _write_json_file(
        _tasks_json_path(repo_root),
        {"tasks": tasks},
    )


def _read_scheduler_state(repo_root: Path) -> Dict[str, Any]:
    data = _read_json_file(_scheduler_state_path(repo_root))
    return data if isinstance(data, dict) else {}


def _status(task: Dict[str, Any]) -> str:
    return str(task.get("status") or "").strip().lower()


def _task_id(task: Dict[str, Any]) -> str:
    return str(
        task.get("task_id")
        or task.get("task_name")
        or task.get("id")
        or ""
    ).strip()


def _count_statuses(tasks: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for task in tasks:
        status = _status(task) or "unknown"
        counts[status] = counts.get(status, 0) + 1

    return dict(sorted(counts.items()))


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _extract_state_queue(state: Dict[str, Any]) -> Dict[str, Any]:
    candidates: List[Any] = [
        state.get("queue"),
        state.get("snapshot"),
        state.get("scheduler"),
        state.get("state"),
    ]

    snapshot = state.get("snapshot")

    if isinstance(snapshot, dict):
        candidates.extend(
            [
                snapshot.get("queue"),
                snapshot.get("scheduler"),
                snapshot.get("state"),
            ]
        )

    for candidate in candidates:
        if isinstance(candidate, dict):
            queue = candidate.get("queue")

            if isinstance(queue, dict):
                return queue

            if any(
                key in candidate
                for key in (
                    "queued_count",
                    "running_count",
                    "ready_queue",
                    "running_tasks",
                    "total_count",
                    "status_counts",
                )
            ):
                return candidate

    return {}


def _state_queue_snapshot(repo_root: Path) -> Dict[str, Any]:
    state = _read_scheduler_state(repo_root)
    queue = _extract_state_queue(state)

    ready_queue = queue.get("ready_queue")
    running_tasks = queue.get("running_tasks")
    status_counts = queue.get("status_counts")

    if not isinstance(ready_queue, list):
        ready_queue = []

    if not isinstance(running_tasks, list):
        running_tasks = []

    if not isinstance(status_counts, dict):
        status_counts = {}

    queued_count = _as_int(queue.get("queued_count"), 0)
    running_count = _as_int(queue.get("running_count"), 0)
    total_count = _as_int(queue.get("total_count"), 0)

    active_from_status = 0

    for key in (
        "queued",
        "ready",
        "retry",
        "retrying",
        "running",
        "replanning",
    ):
        active_from_status += _as_int(status_counts.get(key), 0)

    return {
        "source": (
            "scheduler_state.json"
            if queue
            else (
                "missing"
                if not _scheduler_state_path(repo_root).exists()
                else "unavailable"
            )
        ),
        "queued_count": queued_count,
        "running_count": running_count,
        "total_count": total_count,
        "ready_queue_count": len(ready_queue),
        "running_tasks_count": len(running_tasks),
        "active_status_count": active_from_status,
        "is_empty": not (
            queued_count
            or running_count
            or ready_queue
            or running_tasks
            or active_from_status
        )
        if queue
        else (
            True
            if not _scheduler_state_path(repo_root).exists()
            else None
        ),
    }


def _deps_satisfied(
    task: Dict[str, Any],
    by_id: Dict[str, Dict[str, Any]],
) -> bool:
    deps = task.get("depends_on")

    if not isinstance(deps, list) or not deps:
        return True

    completed = {
        "done",
        "finished",
        "completed",
        "success",
    }

    for dep in deps:
        dep_task = by_id.get(str(dep).strip())

        if not isinstance(dep_task, dict):
            return False

        if _status(dep_task) not in completed:
            return False

    return True


def _ready_count_from_index(tasks: List[Dict[str, Any]]) -> int:
    by_id = {
        _task_id(task): task
        for task in tasks
        if _task_id(task)
    }

    ready_statuses = {
        "queued",
        "ready",
        "retry",
        "retrying",
        "running",
        "replanning",
    }

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

    count = 0

    for task in tasks:
        status = _status(task)

        if not status or status in terminal_statuses:
            continue

        if status not in ready_statuses:
            continue

        if not _deps_satisfied(task, by_id):
            continue

        count += 1

    return count


def _fast_health_payload(repo_root: Path) -> Dict[str, Any]:
    workspace = _workspace_root(repo_root)
    tasks = _read_tasks_index(repo_root)
    status_counts = _count_statuses(tasks)
    scheduler_queue = _state_queue_snapshot(repo_root)

    return {
        "ok": True,
        "system": "ZERO",
        "mode": "fast_runtime_cli",
        "legacy_app_booted": False,
        "runtime_booted": False,
        "workspace": str(workspace),
        "tasks_db_path": str(_tasks_json_path(repo_root)),
        "tasks_dir": str(workspace / "tasks"),
        "runtime_dir": str(workspace / "runtime"),
        "logs_dir": str(workspace / "logs"),
        "scheduler_state_file": str(_scheduler_state_path(repo_root)),
        "memory_root": str(workspace / "memory"),
        "knowledge_root": str(workspace / "knowledge"),
        "cache_root": str(workspace / "cache"),
        "queue": {
            "tasks_index_total_count": len(tasks),
            "tasks_index_ready_count": _ready_count_from_index(tasks),
            "tasks_index_status_counts": status_counts,
            "scheduler_queue": scheduler_queue,
        },
        "components": {
            "router_type": None,
            "step_executor_type": None,
            "planner_type": None,
            "llm_client_type": None,
            "agent_loop_type": None,
            "scheduler_type": "fast_runtime_cli_snapshot",
            "task_repository_type": "tasks_json_snapshot",
            "task_runtime_type": None,
        },
    }


def _fast_runtime_payload(repo_root: Path) -> Dict[str, Any]:
    health = _fast_health_payload(repo_root)

    return {
        "ok": True,
        "mode": "fast_runtime_cli",
        "legacy_app_booted": False,
        "runtime_booted": False,
        "workspace": health.get("workspace"),
        "runtime": {
            "ok": True,
            "app": "ZERO Task OS",
            "workspace_dir": _workspace_dir(),
            "has_scheduler": False,
            "has_agent_loop": False,
        },
        "queue": health.get("queue", {}),
    }


def _fast_runtime_kernel_payload(repo_root: Path) -> Dict[str, Any]:
    """Build the real Runtime Kernel summary without booting app_legacy.py.

    This keeps the fast runtime CLI path lightweight while wiring
    `python app.py runtime kernel` to the same kernel-status builder used by
    the task display path.
    """
    try:
        from core.tasks.runtime_kernel_status import build_runtime_kernel_status

        status = build_runtime_kernel_status()
        if not isinstance(status, dict):
            status = {}

        status.setdefault("ok", False)
        status.setdefault("mode", "fast_runtime_cli_kernel")
        status.setdefault("legacy_app_booted", False)
        status.setdefault("runtime_booted", False)
        status.setdefault("workspace", str(_workspace_root(repo_root)))
        return status
    except Exception as exc:
        return {
            "ok": False,
            "mode": "fast_runtime_cli_kernel",
            "legacy_app_booted": False,
            "runtime_booted": False,
            "workspace": str(_workspace_root(repo_root)),
            "error": f"{exc.__class__.__name__}: {exc}",
            "kernel": {
                "status": "unavailable",
                "total_events": 0,
                "total_invalid": 0,
                "total_noop": 0,
                "total_errors": 0,
                "total_warnings": 0,
                "planner_event_count": 0,
                "execution_event_count": 0,
                "planner_ready": False,
                "execution_ready": False,
            },
            "planner": {"event_count": 0},
            "execution": {"event_count": 0},
        }


def _print_fast_runtime_kernel(repo_root: Path, *, output_json: bool = False) -> None:
    payload = _fast_runtime_kernel_payload(repo_root)

    if output_json:
        _print_json(payload)
        return

    try:
        from core.tasks.runtime_kernel_status import format_runtime_kernel_status

        print(format_runtime_kernel_status(payload))
    except Exception:
        kernel = payload.get("kernel") if isinstance(payload.get("kernel"), dict) else {}
        planner = payload.get("planner") if isinstance(payload.get("planner"), dict) else {}
        execution = payload.get("execution") if isinstance(payload.get("execution"), dict) else {}
        print(f"Runtime Kernel Status: {kernel.get('status', 'unavailable')}")
        print(f"- planner events: {planner.get('event_count', 0)}")
        print(f"- execution events: {execution.get('event_count', 0)}")
        print(f"- total invalid: {kernel.get('total_invalid', 0)}")
        print(f"- total errors: {kernel.get('total_errors', 0)}")
        print(f"- total warnings: {kernel.get('total_warnings', 0)}")


def _fast_replay_payload() -> Dict[str, Any]:
    return {
        "ok": False,
        "mode": "fast_runtime_cli",
        "legacy_app_booted": False,
        "runtime_booted": False,
        "error": "agent_loop not available",
        "input": "replay",
    }


def _create_ingestion_task(
    repo_root: Path,
    *,
    mode: str,
    prompt: str,
) -> Dict[str, Any]:
    tasks = _read_tasks_index(repo_root)

    task_id = f"task_{int(time.time() * 1000)}"

    task = {
        "task_id": task_id,
        "type": mode,
        "title": prompt[:80],
        "goal": prompt,
        "status": "queued",
        "created_at": time.time(),
        "fast_cli_path": True,
        "legacy_app_booted": False,
        "runtime_booted": False,
    }

    tasks.append(task)
    _save_tasks_index(repo_root, tasks)

    return {
        "ok": True,
        "mode": "fast_runtime_cli",
        "created": True,
        "task_id": task_id,
        "status": "queued",
        "input": prompt,
        "task": task,
    }


def _normalized_command(argv: List[str]) -> str:
    parts = [
        str(item).strip()
        for item in argv
        if str(item).strip()
    ]

    if not parts:
        return ""

    return " ".join(parts).strip().lower()


def try_handle_fast_runtime_command(
    argv: List[str],
    *,
    repo_root: Path,
) -> bool:
    command = _normalized_command(argv)

    if command == "health":
        _print_json(_fast_health_payload(repo_root))
        return True

    if command == "runtime":
        _print_json(_fast_runtime_payload(repo_root))
        return True

    if command in {"runtime status", "runtime snapshot"}:
        _print_json(_fast_runtime_payload(repo_root))
        return True

    if command == "runtime kernel":
        _print_fast_runtime_kernel(repo_root, output_json=False)
        return True

    if command in {"runtime kernel --json", "runtime kernel json"}:
        _print_fast_runtime_kernel(repo_root, output_json=True)
        return True

    if command == "replay":
        _print_json(_fast_replay_payload())
        return True

    if argv and argv[0] in {"ask", "chat"}:
        prompt = " ".join(argv[1:]).strip()

        _print_json(
            _create_ingestion_task(
                repo_root,
                mode=argv[0],
                prompt=prompt,
            )
        )

        return True

    return False