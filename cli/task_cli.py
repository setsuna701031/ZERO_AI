from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _workspace_dir() -> str:
    return os.environ.get("ZERO_WORKSPACE", "workspace")


def _workspace_root(repo_root: Path) -> Path:
    workspace = Path(_workspace_dir())
    if workspace.is_absolute():
        return workspace
    return repo_root / workspace


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _tasks_json_path(repo_root: Path) -> Path:
    return _workspace_root(repo_root) / "tasks.json"


def _scheduler_state_path(repo_root: Path) -> Path:
    return _workspace_root(repo_root) / "scheduler_state.json"


def _tasks_dir(repo_root: Path) -> Path:
    return _workspace_root(repo_root) / "tasks"


def _shared_dir(repo_root: Path) -> Path:
    return _workspace_root(repo_root) / "shared"


def _artifact_graph_path(repo_root: Path) -> Path:
    return _shared_dir(repo_root) / "artifact_graph.json"


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
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _write_text_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _read_tasks_index(repo_root: Path) -> List[Dict[str, Any]]:
    data = _read_json_file(_tasks_json_path(repo_root))
    if isinstance(data, dict) and isinstance(data.get("tasks"), list):
        return [item for item in data["tasks"] if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _write_tasks_index(repo_root: Path, tasks: List[Dict[str, Any]]) -> None:
    existing = _read_json_file(_tasks_json_path(repo_root))
    if isinstance(existing, dict):
        existing["tasks"] = tasks
        _write_json_file(_tasks_json_path(repo_root), existing)
    else:
        _write_json_file(_tasks_json_path(repo_root), tasks)


def _read_scheduler_state(repo_root: Path) -> Dict[str, Any]:
    data = _read_json_file(_scheduler_state_path(repo_root))
    return data if isinstance(data, dict) else {}


def _task_id(task: Dict[str, Any]) -> str:
    return str(task.get("task_id") or task.get("task_name") or task.get("id") or "").strip()


def _status(task: Dict[str, Any]) -> str:
    return str(task.get("status") or "").strip().lower()


def _goal(task: Dict[str, Any]) -> str:
    return str(task.get("goal") or task.get("title") or task.get("prompt") or "").strip()


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _rel_path(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _extract_state_queue(state: Dict[str, Any]) -> Dict[str, Any]:
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


def _state_queue_is_empty(state: Dict[str, Any]) -> Optional[bool]:
    if not state:
        return None
    queue = _extract_state_queue(state)
    if not queue:
        return None

    ready_queue = queue.get("ready_queue")
    running_tasks = queue.get("running_tasks")
    status_counts = queue.get("status_counts")
    queued_count = _as_int(queue.get("queued_count"), 0)
    running_count = _as_int(queue.get("running_count"), 0)

    if isinstance(ready_queue, list) and ready_queue:
        return False
    if isinstance(running_tasks, list) and running_tasks:
        return False
    if queued_count > 0 or running_count > 0:
        return False
    if isinstance(status_counts, dict):
        active = sum(_as_int(status_counts.get(key), 0) for key in ("queued", "ready", "retry", "retrying", "running", "replanning"))
        if active > 0:
            return False

    if isinstance(ready_queue, list) or isinstance(running_tasks, list) or "queued_count" in queue or "running_count" in queue or isinstance(status_counts, dict):
        return True
    return None


def _live_runtime_marker_exists(repo_root: Path) -> bool:
    workspace = _workspace_root(repo_root)
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


def _runtime_queue_empty(repo_root: Path) -> bool:
    state_path = _scheduler_state_path(repo_root)
    state_empty = _state_queue_is_empty(_read_scheduler_state(repo_root))
    if state_empty is not None:
        return bool(state_empty)
    if not state_path.exists():
        return not _live_runtime_marker_exists(repo_root)
    return not bool(_ready_tasks_from_index(repo_root))


def _deps_satisfied(task: Dict[str, Any], by_id: Dict[str, Dict[str, Any]]) -> bool:
    deps = task.get("depends_on")
    if not isinstance(deps, list) or not deps:
        return True
    for dep in deps:
        dep_task = by_id.get(str(dep).strip())
        if not isinstance(dep_task, dict):
            return False
        if _status(dep_task) not in {"done", "finished", "completed", "success"}:
            return False
    return True


def _ready_tasks_from_index(repo_root: Path) -> List[Dict[str, Any]]:
    tasks = _read_tasks_index(repo_root)
    by_id = {_task_id(task): task for task in tasks if _task_id(task)}
    ready: List[Dict[str, Any]] = []
    for task in tasks:
        status = _status(task)
        if not status or status in {"finished", "done", "success", "completed", "failed", "error", "cancelled", "canceled"}:
            continue
        if status not in {"queued", "ready", "retry", "retrying", "running", "replanning"}:
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
    return max(1, count)


def _task_dir(repo_root: Path, task_id: str) -> Path:
    return _tasks_dir(repo_root) / task_id


def _safe_artifact_name(task_id: str, suffix: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in task_id)
    return f"{clean}_{suffix}"


def _resolve_repo_path(repo_root: Path, raw_path: str) -> Path:
    text = str(raw_path or "").strip().strip('"').strip("'")
    text = text.replace("\\", os.sep).replace("/", os.sep)
    path = Path(text)
    if path.is_absolute():
        return path
    return repo_root / path


def _extract_first_path_after(goal: str, keyword: str) -> Optional[str]:
    pattern = re.compile(rf"{re.escape(keyword)}\s+([^\s]+)", re.IGNORECASE)
    match = pattern.search(goal)
    if match:
        return match.group(1).strip()
    return None


def _extract_source_path(repo_root: Path, goal: str, default_name: str = "input.txt") -> Path:
    for keyword in ("from", "summarize"):
        raw = _extract_first_path_after(goal, keyword)
        if raw and "." in raw:
            return _resolve_repo_path(repo_root, raw)
    for raw in re.findall(r"[\w./\\-]+\.[A-Za-z0-9]+", goal):
        if "summary" in raw.lower() or "report" in raw.lower():
            continue
        return _resolve_repo_path(repo_root, raw)
    return _shared_dir(repo_root) / default_name


def _extract_output_path(repo_root: Path, goal: str, default_filename: str) -> Path:
    raw = _extract_first_path_after(goal, "into")
    if raw and "." in raw:
        return _resolve_repo_path(repo_root, raw)

    candidates = re.findall(r"[\w./\\-]+\.[A-Za-z0-9]+", goal)
    for candidate in reversed(candidates):
        lowered = candidate.lower()
        if default_filename.lower() in lowered or "summary" in lowered or "report" in lowered:
            return _resolve_repo_path(repo_root, candidate)

    return _shared_dir(repo_root) / default_filename


def _compact_summary(text: str, limit: int = 260) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return "No input content was available."
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."


def _artifact_node_type(path: Path, artifact_type: str = "") -> str:
    lowered = path.name.lower()
    artifact_lower = artifact_type.lower()
    if "summary" in lowered or "summary" in artifact_lower:
        return "summary"
    if "report" in lowered or "markdown" in artifact_lower:
        return "report"
    if lowered.endswith(".py"):
        return "python_file"
    if lowered.endswith(".txt"):
        return "text"
    return artifact_lower or "artifact"


def _update_artifact_graph(repo_root: Path, task: Dict[str, Any], artifact: Dict[str, Any]) -> None:
    artifact_path_raw = artifact.get("artifact_path")
    if not artifact_path_raw:
        return

    graph_path = _artifact_graph_path(repo_root)
    existing = _read_json_file(graph_path)
    if not isinstance(existing, dict):
        existing = {"version": 1, "nodes": [], "edges": [], "events": []}

    nodes = existing.get("nodes")
    edges = existing.get("edges")
    events = existing.get("events")
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []
    if not isinstance(events, list):
        events = []

    node_by_path = {str(node.get("artifact")): node for node in nodes if isinstance(node, dict)}
    edge_keys = {
        (str(edge.get("from")), str(edge.get("to")), str(edge.get("task_id")))
        for edge in edges
        if isinstance(edge, dict)
    }

    output_path = Path(str(artifact_path_raw))
    output_rel = _rel_path(repo_root, output_path)
    input_path_raw = artifact.get("input_path")
    input_rel = None
    if input_path_raw:
        input_rel = _rel_path(repo_root, Path(str(input_path_raw)))

    now = time.time()
    task_id = _task_id(task)
    artifact_type = str(artifact.get("artifact_type") or "")

    if input_rel and input_rel not in node_by_path:
        input_node = {
            "artifact": input_rel,
            "type": "input",
            "first_seen_at": now,
            "last_seen_at": now,
        }
        nodes.append(input_node)
        node_by_path[input_rel] = input_node
    elif input_rel:
        node_by_path[input_rel]["last_seen_at"] = now

    if output_rel not in node_by_path:
        output_node = {
            "artifact": output_rel,
            "type": _artifact_node_type(output_path, artifact_type),
            "artifact_type": artifact_type,
            "first_seen_at": now,
            "last_seen_at": now,
            "producer_task_id": task_id,
        }
        nodes.append(output_node)
        node_by_path[output_rel] = output_node
    else:
        node_by_path[output_rel]["last_seen_at"] = now
        node_by_path[output_rel]["artifact_type"] = artifact_type
        node_by_path[output_rel]["producer_task_id"] = task_id

    if input_rel:
        edge_key = (input_rel, output_rel, task_id)
        if edge_key not in edge_keys:
            edges.append(
                {
                    "from": input_rel,
                    "to": output_rel,
                    "task_id": task_id,
                    "operation": artifact_type or "artifact_write",
                    "created_at": now,
                }
            )

    events.append(
        {
            "task_id": task_id,
            "goal": _goal(task),
            "input": input_rel,
            "output": output_rel,
            "artifact_type": artifact_type,
            "created_at": now,
        }
    )

    existing["version"] = 1
    existing["updated_at"] = now
    existing["nodes"] = nodes
    existing["edges"] = edges
    existing["events"] = events[-200:]
    _write_json_file(graph_path, existing)


def _build_python_hello_world_artifact(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    task_id = _task_id(task)
    artifact_path = _shared_dir(repo_root) / _safe_artifact_name(task_id, "hello_world.py")
    code = 'print("Hello, world!")\n'
    _write_text_file(artifact_path, code)
    return {
        "ok": True,
        "artifact_type": "python_file",
        "artifact_path": str(artifact_path),
        "content_preview": code,
        "message": "Created Python hello world artifact.",
    }


def _build_summary_artifact(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    goal = _goal(task)
    input_path = _extract_source_path(repo_root, goal, "input.txt")
    output_path = _extract_output_path(repo_root, goal, "summary.txt")
    source_text = _read_text_file(input_path)
    summary = f"Summary: {_compact_summary(source_text)}\n"
    _write_text_file(output_path, summary)
    return {
        "ok": True,
        "artifact_type": "summary_text",
        "input_path": str(input_path),
        "artifact_path": str(output_path),
        "content_preview": summary,
        "message": "Created summary artifact.",
    }


def _build_markdown_report_artifact(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    goal = _goal(task)
    input_path = _extract_source_path(repo_root, goal, "input.txt")
    output_path = _extract_output_path(repo_root, goal, "report.md")
    source_text = _read_text_file(input_path)
    summary = _compact_summary(source_text, limit=420)
    text = (
        "# Report\n\n"
        "## Source\n\n"
        f"- Input: `{input_path.as_posix()}`\n"
        f"- Generated by: ZERO thin execution bridge v1\n\n"
        "## Summary\n\n"
        f"{summary}\n\n"
        "## Execution Notes\n\n"
        "- Task was accepted through the fast CLI path.\n"
        "- Markdown report artifact was written by the thin artifact writer.\n"
        "- Legacy runtime boot was avoided for this smoke path.\n"
    )
    _write_text_file(output_path, text)
    return {
        "ok": True,
        "artifact_type": "markdown_report",
        "input_path": str(input_path),
        "artifact_path": str(output_path),
        "content_preview": text,
        "message": "Created markdown report artifact.",
    }


def _build_system_analysis_artifact(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    task_id = _task_id(task)
    artifact_path = _shared_dir(repo_root) / _safe_artifact_name(task_id, "system_analysis.md")
    tasks = _read_tasks_index(repo_root)
    queued = sum(1 for item in tasks if _status(item) == "queued")
    finished = sum(1 for item in tasks if _status(item) == "finished")
    failed = sum(1 for item in tasks if _status(item) == "failed")
    text = (
        "# ZERO System Analysis\n\n"
        "- Thin launcher: active\n"
        "- Fast CLI path: active\n"
        "- Legacy boot avoided for ask/chat/task run/help/runtime/health/replay\n"
        f"- Total tasks index entries: {len(tasks)}\n"
        f"- Queued tasks: {queued}\n"
        f"- Finished tasks: {finished}\n"
        f"- Failed tasks: {failed}\n\n"
        "Current state: ingestion shell is working. Next layer is planner/executor bridge.\n"
    )
    _write_text_file(artifact_path, text)
    return {
        "ok": True,
        "artifact_type": "markdown_report",
        "artifact_path": str(artifact_path),
        "content_preview": text,
        "message": "Created system analysis artifact.",
    }


def _build_generic_ingestion_artifact(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    task_id = _task_id(task)
    artifact_path = _shared_dir(repo_root) / _safe_artifact_name(task_id, "result.txt")
    text = (
        "ZERO thin execution bridge v1 accepted this task.\n\n"
        f"task_id: {task_id}\n"
        f"type: {task.get('type')}\n"
        f"goal: {_goal(task)}\n\n"
        "Planner/executor runtime is not attached in this bridge yet.\n"
    )
    _write_text_file(artifact_path, text)
    return {
        "ok": True,
        "artifact_type": "text_result",
        "artifact_path": str(artifact_path),
        "content_preview": text,
        "message": "Created generic thin execution artifact.",
    }


def _execute_ingestion_task(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    task_type = str(task.get("type") or "").strip().lower()
    goal = _goal(task)
    lowered = goal.lower()

    if ("markdown" in lowered or ".md" in lowered or "report" in lowered) and ("generate" in lowered or "create" in lowered or "建立" in goal or "產生" in goal or "report" in lowered):
        artifact = _build_markdown_report_artifact(repo_root, task)
    elif task_type == "summarize" or "summarize" in lowered or "summary" in lowered or "摘要" in goal:
        artifact = _build_summary_artifact(repo_root, task)
    elif "hello world" in lowered and ("python" in lowered or "py" in lowered):
        artifact = _build_python_hello_world_artifact(repo_root, task)
    elif "分析" in goal or "system" in lowered or "目前系統" in goal:
        artifact = _build_system_analysis_artifact(repo_root, task)
    else:
        artifact = _build_generic_ingestion_artifact(repo_root, task)

    _update_artifact_graph(repo_root, task, artifact)

    result = {
        "ok": bool(artifact.get("ok", False)),
        "task_id": _task_id(task),
        "type": task_type,
        "goal": goal,
        "runtime_mode": "thin_execution_bridge_v1",
        "planner_attached": False,
        "executor_attached": "thin_artifact_writer",
        "artifact": artifact,
        "artifact_graph_path": str(_artifact_graph_path(repo_root)),
        "message": f"Thin execution bridge handled task: {goal}",
    }

    task_dir = _task_dir(repo_root, _task_id(task))
    result_path = task_dir / "result.json"
    snapshot_path = task_dir / "task_snapshot.json"
    runtime_state_path = task_dir / "runtime_state.json"

    task["result_path"] = str(result_path)
    task["snapshot_path"] = str(snapshot_path)
    task["runtime_state_path"] = str(runtime_state_path)
    task["artifact_path"] = artifact.get("artifact_path")
    task["artifact_graph_path"] = str(_artifact_graph_path(repo_root))

    _write_json_file(result_path, result)
    _write_json_file(snapshot_path, task)
    _write_json_file(
        runtime_state_path,
        {
            "ok": True,
            "task_id": _task_id(task),
            "status": "finished",
            "runtime_mode": "thin_execution_bridge_v1",
            "artifact_path": artifact.get("artifact_path"),
            "artifact_graph_path": str(_artifact_graph_path(repo_root)),
            "result_path": str(result_path),
        },
    )

    return result


def _run_ingestion_tasks(repo_root: Path, count: int) -> Optional[Dict[str, Any]]:
    tasks = _read_tasks_index(repo_root)
    if not tasks:
        return None

    executed_results: List[Dict[str, Any]] = []
    executed_count = 0
    now = time.time()

    for task in tasks:
        if executed_count >= count:
            break
        if _status(task) not in {"queued", "ready", "retry", "retrying"}:
            continue
        task_type = str(task.get("type") or "").strip().lower()
        goal = _goal(task).lower()
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
        if task_type not in {"ask", "chat", "summarize", "report", "markdown_report"} and not routable_goal:
            continue

        task["status"] = "running"
        task["started_at"] = now
        task["runtime_booted"] = False
        task["fast_cli_path"] = True

        result = _execute_ingestion_task(repo_root, task)

        task["status"] = "finished" if result.get("ok") else "failed"
        task["finished_at"] = time.time()
        task["result"] = result
        executed_results.append(result)
        executed_count += 1

    if executed_count <= 0:
        return None

    _write_tasks_index(repo_root, tasks)
    return {
        "ok": True,
        "mode": "thin_execution_bridge_v1",
        "fast_cli_path": True,
        "legacy_app_booted": False,
        "runtime_booted": False,
        "executed_count": executed_count,
        "executed_results": executed_results,
    }


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




def _format_artifact_graph(repo_root: Path) -> str:
    graph = _read_json_file(_artifact_graph_path(repo_root))
    if not isinstance(graph, dict):
        return "artifact_graph.json not found."

    nodes = graph.get("nodes")
    edges = graph.get("edges")
    events = graph.get("events")
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []
    if not isinstance(events, list):
        events = []

    lines: List[str] = []
    lines.append("ZERO Artifact Graph")
    lines.append("")
    lines.append(f"nodes: {len(nodes)}")
    lines.append(f"edges: {len(edges)}")
    lines.append(f"events: {len(events)}")
    lines.append("")

    if edges:
        lines.append("Edges:")
        for edge in edges[-30:]:
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("from") or "")
            target = str(edge.get("to") or "")
            op = str(edge.get("operation") or "artifact_write")
            task_id = str(edge.get("task_id") or "")
            lines.append(f"- {source} -> {target} [{op}] {task_id}")
        lines.append("")

    if nodes:
        lines.append("Nodes:")
        for node in nodes[-30:]:
            if not isinstance(node, dict):
                continue
            artifact = str(node.get("artifact") or "")
            node_type = str(node.get("type") or "artifact")
            producer = str(node.get("producer_task_id") or "")
            if producer:
                lines.append(f"- {artifact} ({node_type}) producer={producer}")
            else:
                lines.append(f"- {artifact} ({node_type})")

    return "\n".join(lines)


def _try_handle_fast_task_graph(argv: List[str], repo_root: Path) -> bool:
    if len(argv) not in {2, 3}:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False

    action = str(argv[1]).strip().lower()
    if action not in {"graph", "artifact-graph", "artifacts"}:
        return False

    output_mode = str(argv[2]).strip().lower() if len(argv) == 3 else "text"
    graph = _read_json_file(_artifact_graph_path(repo_root))

    if output_mode in {"json", "--json"}:
        _print_json(graph if isinstance(graph, dict) else {"ok": False, "error": "artifact_graph.json not found"})
        return True

    print(_format_artifact_graph(repo_root))
    return True


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

    ingestion_result = _run_ingestion_tasks(repo_root, count)
    if ingestion_result is not None:
        _print_json(ingestion_result)
        return True

    if not _runtime_queue_empty(repo_root):
        return False

    _print_json(_empty_manual_ticks(count))
    return True


def try_handle_fast_task_command(argv: List[str], *, repo_root: Path) -> bool:
    clean_argv = [str(item) for item in argv if str(item).strip()]

    if _try_handle_fast_task_graph(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_run(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_list(clean_argv, repo_root):
        return True

    return False
