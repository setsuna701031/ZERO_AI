from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.artifacts.registry import artifact_graph_path, format_artifact_graph, read_json_file
from core.runtime.thin_runtime_bridge import drain_ingestion_tasks, run_ingestion_tasks
from core.tasks.task_index import (
    read_tasks_index,
    runtime_queue_empty,
    shared_dir,
    task_goal,
    task_id,
    task_status,
    write_tasks_index,
)


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


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
    return max(1, count)


def _empty_tick_result(tick: int) -> Dict[str, Any]:
    return {
        "ok": True,
        "scheduler_build": "APP_THIN_FAST_EMPTY_QUEUE_V4_MISSING_STATE_SAFE",
        "tick": tick,
        "rounds_used": 1,
        "max_scheduler_rounds_per_tick": 50,
        "synced_task_ids": [],
        "dispatched_count": 0,
        "executed_count": 0,
        "executed_results": [],
        "snapshot": {
            "queue": {"queued_count": 0, "total_count": 0, "status_counts": {}, "next_task": None},
            "workers": {"max_workers": 1, "busy_workers": 0, "free_workers": 1, "running_count": 0, "running_tasks": []},
            "queued_count": 0,
            "total_count": 0,
            "running_count": 0,
            "ready_queue": [],
            "running_tasks": [],
        },
        "fast_cli_path": True,
        "legacy_app_booted": False,
        "queue_source": "scheduler_state_or_recent_live_markers",
    }


def _empty_manual_ticks(count: int) -> Dict[str, Any]:
    return {
        "ok": True,
        "count": count,
        "results": [{"tick_index": i + 1, "result": _empty_tick_result(i + 1)} for i in range(count)],
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
        current_task_id = task_id(task)
        status = task_status(task) or "unknown"
        goal = " ".join(task_goal(task).split())
        deps = task.get("depends_on")
        dep_suffix = ""
        if isinstance(deps, list) and deps:
            dep_suffix = f" depends_on={','.join(str(item) for item in deps)}"
        if len(goal) > 70:
            goal = goal[:67] + "..."
        rows.append((current_task_id, status, goal + dep_suffix))

    task_id_width = max(len("task_id"), min(28, max(len(row[0]) for row in rows)))
    status_width = max(len("status"), min(14, max(len(row[1]) for row in rows)))

    print(f"{'task_id':<{task_id_width}}  {'status':<{status_width}}  goal")
    print("-" * max(80, task_id_width + status_width + 8))
    for current_task_id, status, goal in rows:
        print(f"{current_task_id:<{task_id_width}}  {status:<{status_width}}  {goal}")


def _try_handle_fast_task_graph(argv: List[str], repo_root: Path) -> bool:
    if len(argv) not in {2, 3}:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False

    action = str(argv[1]).strip().lower()
    if action not in {"graph", "artifact-graph", "artifacts"}:
        return False

    output_mode = str(argv[2]).strip().lower() if len(argv) == 3 else "text"
    graph_path = artifact_graph_path(shared_dir(repo_root))
    graph = read_json_file(graph_path)

    if output_mode in {"json", "--json"}:
        _print_json(graph if isinstance(graph, dict) else {"ok": False, "error": "artifact_graph.json not found"})
        return True

    print(format_artifact_graph(shared_dir(repo_root)))
    return True


def _new_task(task_id_value: str, goal: str, depends_on: Optional[List[str]] = None) -> Dict[str, Any]:
    task: Dict[str, Any] = {
        "task_id": task_id_value,
        "type": "ask",
        "goal": goal,
        "status": "queued",
        "created_at": time.time(),
        "fast_cli_path": True,
        "legacy_app_booted": False,
        "runtime_booted": False,
    }
    if depends_on:
        task["depends_on"] = depends_on
    return task


def _try_handle_fast_task_dag_smoke(argv: List[str], repo_root: Path) -> bool:
    if len(argv) != 2:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() not in {"dag-smoke", "dependency-smoke", "dag"}:
        return False

    stamp = int(time.time() * 1000)
    task_a = f"task_{stamp}_dag_a"
    task_b = f"task_{stamp}_dag_b"
    task_c = f"task_{stamp}_dag_c"

    new_tasks = [
        _new_task(
            task_a,
            "summarize workspace/shared/input.txt into workspace/shared/dag_summary.txt",
        ),
        _new_task(
            task_b,
            "generate a markdown report from workspace/shared/dag_summary.txt into workspace/shared/dag_report.md",
            depends_on=[task_a],
        ),
        _new_task(
            task_c,
            "summarize workspace/shared/dag_report.md into workspace/shared/dag_final.txt",
            depends_on=[task_b],
        ),
    ]

    tasks = read_tasks_index(repo_root)
    tasks.extend(new_tasks)
    write_tasks_index(repo_root, tasks)

    _print_json(
        {
            "ok": True,
            "mode": "dag_smoke_v1",
            "created_count": len(new_tasks),
            "task_ids": [task_a, task_b, task_c],
            "message": "Created DAG smoke tasks. Run `python app.py task run 3` to execute dependency order.",
        }
    )
    return True


def _try_handle_fast_task_list(argv: List[str], repo_root: Path) -> bool:
    if len(argv) != 2:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() != "list":
        return False
    _print_task_table(read_tasks_index(repo_root))
    return True




def _try_handle_fast_task_drain(argv: List[str], repo_root: Path) -> bool:
    if len(argv) not in {2, 3}:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() not in {"drain", "auto-drain", "run-all"}:
        return False

    raw_max_rounds = str(argv[2]).strip() if len(argv) == 3 else "50"
    try:
        max_rounds = int(raw_max_rounds)
    except Exception:
        max_rounds = 50

    _print_json(drain_ingestion_tasks(repo_root, max_rounds=max_rounds))
    return True


def _try_handle_fast_task_run(argv: List[str], repo_root: Path) -> bool:
    count = _parse_task_run(argv)
    if count is None:
        return False

    ingestion_result = run_ingestion_tasks(repo_root, count)
    if ingestion_result is not None:
        _print_json(ingestion_result)
        return True

    if not runtime_queue_empty(repo_root):
        return False

    _print_json(_empty_manual_ticks(count))
    return True


def try_handle_fast_task_command(argv: List[str], *, repo_root: Path) -> bool:
    clean_argv = [str(item) for item in argv if str(item).strip()]

    if _try_handle_fast_task_graph(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_dag_smoke(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_drain(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_run(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_list(clean_argv, repo_root):
        return True

    return False
