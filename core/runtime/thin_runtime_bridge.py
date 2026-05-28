from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.artifacts.registry import update_artifact_graph, write_json_file
from core.artifacts.writers import (
    build_generic_ingestion_artifact,
    build_markdown_report_artifact,
    build_python_hello_world_artifact,
    build_summary_artifact,
    build_system_analysis_artifact,
)
from core.tasks.task_index import (
    deps_satisfied,
    read_tasks_index,
    shared_dir,
    task_goal,
    task_id,
    task_status,
    tasks_dir,
    write_tasks_index,
)


def task_dir(repo_root: Path, task_name: str) -> Path:
    return tasks_dir(repo_root) / task_name


def is_fast_routable_task(task: Dict[str, Any]) -> bool:
    task_type = str(task.get("type") or "").strip().lower()
    goal = task_goal(task).lower()
    routable_goal = any(
        marker in goal
        for marker in (
            "hello world",
            "summarize",
            "summary",
            "markdown report",
            "report.md",
            "generate a markdown",
            "create a markdown",
            "目前系統",
            "system",
        )
    )
    return task_type in {"ask", "chat", "summarize", "report", "markdown_report"} or routable_goal


def select_artifact_writer(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    current_task_id = task_id(task)
    task_type = str(task.get("type") or "").strip().lower()
    goal = task_goal(task)
    lowered = goal.lower()
    current_shared_dir = shared_dir(repo_root)

    if ("markdown" in lowered or ".md" in lowered or "report" in lowered) and (
        "generate" in lowered
        or "create" in lowered
        or "建立" in goal
        or "產生" in goal
        or "report" in lowered
    ):
        return build_markdown_report_artifact(repo_root, current_shared_dir, goal)

    if task_type == "summarize" or "summarize" in lowered or "summary" in lowered or "摘要" in goal:
        return build_summary_artifact(repo_root, current_shared_dir, goal)

    if "hello world" in lowered and ("python" in lowered or "py" in lowered):
        return build_python_hello_world_artifact(repo_root, current_shared_dir, current_task_id)

    if "分析" in goal or "system" in lowered or "目前系統" in goal:
        tasks = read_tasks_index(repo_root)
        queued = sum(1 for item in tasks if task_status(item) == "queued")
        finished = sum(1 for item in tasks if task_status(item) == "finished")
        failed = sum(1 for item in tasks if task_status(item) == "failed")
        return build_system_analysis_artifact(
            repo_root=repo_root,
            shared_dir=current_shared_dir,
            task_id=current_task_id,
            total_tasks=len(tasks),
            queued=queued,
            finished=finished,
            failed=failed,
        )

    return build_generic_ingestion_artifact(current_shared_dir, current_task_id, task_type, goal)


def execute_ingestion_task(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    task_type = str(task.get("type") or "").strip().lower()
    goal = task_goal(task)
    current_task_id = task_id(task)
    current_shared_dir = shared_dir(repo_root)

    artifact = select_artifact_writer(repo_root, task)
    graph_path = update_artifact_graph(
        repo_root=repo_root,
        shared_dir=current_shared_dir,
        task_id=current_task_id,
        goal=goal,
        artifact=artifact,
    )

    result = {
        "ok": bool(artifact.get("ok", False)),
        "task_id": current_task_id,
        "type": task_type,
        "goal": goal,
        "runtime_mode": "thin_execution_bridge_v1",
        "planner_attached": False,
        "executor_attached": "thin_artifact_writer",
        "artifact": artifact,
        "artifact_graph_path": str(graph_path),
        "message": f"Thin execution bridge handled task: {goal}",
    }

    current_task_dir = task_dir(repo_root, current_task_id)
    result_path = current_task_dir / "result.json"
    snapshot_path = current_task_dir / "task_snapshot.json"
    runtime_state_path = current_task_dir / "runtime_state.json"

    task["result_path"] = str(result_path)
    task["snapshot_path"] = str(snapshot_path)
    task["runtime_state_path"] = str(runtime_state_path)
    task["artifact_path"] = artifact.get("artifact_path")
    task["artifact_graph_path"] = str(graph_path)

    write_json_file(result_path, result)
    write_json_file(snapshot_path, task)
    write_json_file(
        runtime_state_path,
        {
            "ok": True,
            "task_id": current_task_id,
            "status": "finished",
            "runtime_mode": "thin_execution_bridge_v1",
            "artifact_path": artifact.get("artifact_path"),
            "artifact_graph_path": str(graph_path),
            "result_path": str(result_path),
        },
    )

    return result


def run_ingestion_tasks(repo_root: Path, count: int) -> Optional[Dict[str, Any]]:
    tasks = read_tasks_index(repo_root)
    if not tasks:
        return None

    executed_results: List[Dict[str, Any]] = []
    skipped_blocked: List[Dict[str, Any]] = []
    executed_count = 0
    now = time.time()

    # The dict values point to the same task dictionaries in `tasks`.
    # Updating a producer to finished in this loop immediately unlocks dependents later in the same pass.
    by_id = {task_id(task): task for task in tasks if task_id(task)}

    for task in tasks:
        if executed_count >= count:
            break
        if task_status(task) not in {"queued", "ready", "retry", "retrying"}:
            continue
        if not is_fast_routable_task(task):
            continue

        current_task_id = task_id(task)
        if not deps_satisfied(task, by_id):
            skipped_blocked.append(
                {
                    "task_id": current_task_id,
                    "goal": task_goal(task),
                    "depends_on": task.get("depends_on"),
                    "status": task_status(task),
                }
            )
            continue

        task["status"] = "running"
        task["started_at"] = now
        task["runtime_booted"] = False
        task["fast_cli_path"] = True

        result = execute_ingestion_task(repo_root, task)

        task["status"] = "finished" if result.get("ok") else "failed"
        task["finished_at"] = time.time()
        task["result"] = result
        executed_results.append(result)
        executed_count += 1

    if executed_count <= 0:
        if skipped_blocked:
            return {
                "ok": True,
                "mode": "thin_execution_bridge_v1",
                "fast_cli_path": True,
                "legacy_app_booted": False,
                "runtime_booted": False,
                "executed_count": 0,
                "executed_results": [],
                "blocked_count": len(skipped_blocked),
                "blocked_tasks": skipped_blocked,
                "message": "No dependency-ready tasks were executable.",
            }
        return None

    write_tasks_index(repo_root, tasks)
    return {
        "ok": True,
        "mode": "thin_execution_bridge_v1",
        "fast_cli_path": True,
        "legacy_app_booted": False,
        "runtime_booted": False,
        "executed_count": executed_count,
        "executed_results": executed_results,
        "blocked_count": len(skipped_blocked),
        "blocked_tasks": skipped_blocked,
    }
