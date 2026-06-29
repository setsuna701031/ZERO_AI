from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.artifacts.registry import artifact_graph_path, format_artifact_graph, read_json_file
from core.runtime.runtime_route_keys import RuntimeRouteKeys
from core.runtime.runtime_route_registry import default_runtime_route_registry
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


def _run_via_mainline(repo_root: Path, *, entrypoint: str, runner: Any, goal: str, request: Dict[str, Any] | None = None) -> Any:
    route_key = RuntimeRouteKeys.CLI_TASK_DRAIN if entrypoint.endswith(".drain") else RuntimeRouteKeys.CLI_TASK_RUN
    registry = default_runtime_route_registry()
    registry.register(
        route_key,
        lambda _request, _workspace_root, _goal: runner,
        {"entrypoint": entrypoint, "component": "task_cli"},
    )
    return registry.run(
        route_key=route_key,
        request=request,
        workspace_root=shared_dir(repo_root).parent,
        goal=goal,
    )


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


def _parse_task_run_selector(argv: List[str]) -> Optional[str]:
    if len(argv) < 3:
        return None
    if str(argv[0]).strip().lower() != "task":
        return None
    if str(argv[1]).strip().lower() != "run":
        return None
    selector = str(argv[2]).strip()
    if not selector:
        return None
    lowered = selector.lower()
    if lowered in {"latest", "newest", "last", "next", "oldest", "first"}:
        return lowered
    if selector.startswith("task_") or selector.startswith("agent-runtime-") or selector.startswith("planner_prt_"):
        return selector
    return None


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


def _collapse_ws(value: Any) -> str:
    return " ".join(str(value or "").split())


def _shorten_identifier(value: Any, *, max_width: int = 24) -> str:
    text = _collapse_ws(value)
    if len(text) <= max_width:
        return text

    # Keep task ids readable for humans while hiding runtime fingerprints by
    # default.  Full ids are still available through `task list --verbose` or
    # `task list --raw`.
    if text.startswith("agent-runtime-"):
        remainder = text.removeprefix("agent-runtime-")
        left, sep, right = remainder.partition("-runtime-")
        if sep:
            left_tail = left[:8]
            right_tail = right[-8:] if right else ""
            return f"agent-{left_tail}…{right_tail}"

    if text.startswith("planner_prt_") and "-runtime-" in text:
        left, right = text.split("-runtime-", 1)
        left_tail = left.replace("planner_prt_", "")[:8]
        right_tail = right[-8:] if right else ""
        return f"prt-{left_tail}…{right_tail}"

    if max_width <= 8:
        return text[:max_width]
    head = max_width - 9
    return f"{text[:head]}…{text[-8:]}"


def _shorten_text(value: Any, *, max_width: int = 72) -> str:
    text = _collapse_ws(value)
    if len(text) <= max_width:
        return text
    return text[: max(1, max_width - 3)] + "..."


def _task_sort_key(task: Dict[str, Any]) -> Tuple[float, str]:
    created = task.get("created_at") or task.get("created") or task.get("timestamp") or 0
    try:
        created_value = float(created)
    except Exception:
        created_value = 0.0
    return (created_value, str(task_id(task)))


def _task_runtime_hint(task: Dict[str, Any]) -> str:
    for key in (
        "runtime_session_id",
        "runtime_id",
        "session_id",
        "goal_lineage_id",
        "package_id",
    ):
        value = task.get(key)
        if value:
            return _shorten_identifier(value, max_width=20)
    return ""


def _queued_status(task: Dict[str, Any]) -> str:
    return str(task_status(task) or task.get("status") or "").strip().lower()


def _has_executable_steps(task: Dict[str, Any]) -> bool:
    steps = task.get("steps")
    if not isinstance(steps, list) or not steps:
        return False
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_type = str(step.get("type") or "").strip().lower()
        if step_type:
            return True
    return False


def _route_invalid_reason(task: Dict[str, Any]) -> str:
    route = task.get("route")
    if not isinstance(route, dict):
        return ""
    if route.get("ok") is False:
        error = _collapse_ws(route.get("error"))
        return "route failed" + (f": {error}" if error else "")
    if route.get("component_contract_mismatch") is True:
        error = _collapse_ws(route.get("error"))
        return "router contract mismatch" + (f": {error}" if error else "")
    return ""


def _invalid_goal_reason(task: Dict[str, Any]) -> str:
    goal = _collapse_ws(task_goal(task) or task.get("goal") or task.get("title"))
    if not goal:
        return "missing goal"
    if goal.lower() in {"task name:", "task name", "untitled task", "new task"}:
        return f"placeholder goal: {goal}"
    return ""


def _queued_invalid_reason(task: Dict[str, Any]) -> str:
    if not isinstance(task, dict):
        return "not a task record"

    status = _queued_status(task)
    if status not in {"queued", "ready", "retry", "retrying"}:
        return ""

    route_reason = _route_invalid_reason(task)
    if route_reason:
        return route_reason

    # A queued record without hydrated steps is not automatically invalid.
    # Legacy scheduler/runtime-owned records often appear this way in the task
    # index and should be reported as stale/non-fast queued for inspection, not
    # archived as broken zombies by the default cleanup path.
    goal_reason = _invalid_goal_reason(task)
    if goal_reason:
        return goal_reason

    result_exists = task.get("result_exists") is True
    no_progress = not task.get("results") and not task.get("step_results") and not task.get("execution_log")
    if result_exists and no_progress and task.get("fast_cli_path") is not True:
        return "queued task already has result snapshot but no execution progress"

    return ""


def _display_task_status(task: Dict[str, Any]) -> str:
    reason = _queued_invalid_reason(task)
    if reason:
        return "queued_invalid"
    return str(task_status(task) or "unknown")


def _find_task_by_id(tasks: List[Dict[str, Any]], selector: str) -> Optional[Dict[str, Any]]:
    for task in tasks:
        if isinstance(task, dict) and task_id(task) == selector:
            return task
    return None


def _invalid_queued_tasks(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [task for task in tasks if isinstance(task, dict) and _queued_invalid_reason(task)]


def _print_task_table(
    tasks: List[Dict[str, Any]],
    *,
    verbose: bool = False,
    raw: bool = False,
    limit: Optional[int] = 40,
) -> None:
    if not tasks:
        print("目前沒有 task。")
        return

    ordered = sorted(tasks, key=_task_sort_key)
    total_count = len(ordered)
    if limit is not None and limit > 0 and total_count > limit:
        ordered = ordered[-limit:]

    if raw:
        _print_json(ordered)
        return

    rows: List[Tuple[str, str, str, str]] = []
    for task in ordered:
        full_task_id = task_id(task)
        display_task_id = full_task_id if verbose else _shorten_identifier(full_task_id, max_width=24)
        status = _shorten_text(_display_task_status(task), max_width=14)
        goal = _shorten_text(task_goal(task), max_width=90 if verbose else 72)
        deps = task.get("depends_on")
        dep_suffix = ""
        if isinstance(deps, list) and deps:
            dep_ids = [_shorten_identifier(item, max_width=18) for item in deps]
            dep_suffix = f" depends_on={','.join(dep_ids)}"
        meta = ""
        if verbose:
            meta = _task_runtime_hint(task)
        rows.append((display_task_id, status, meta, goal + dep_suffix))

    task_id_width = max(len("task_id"), min(32 if verbose else 24, max(len(row[0]) for row in rows)))
    status_width = max(len("status"), min(14, max(len(row[1]) for row in rows)))
    meta_width = max(len("runtime"), min(20, max((len(row[2]) for row in rows), default=0))) if verbose else 0

    if limit is not None and limit > 0 and total_count > len(ordered):
        print(f"Showing latest {len(ordered)} of {total_count} tasks. Use `task list --all` or `task list --verbose --all` for more.")

    if verbose:
        print(f"{'task_id':<{task_id_width}}  {'status':<{status_width}}  {'runtime':<{meta_width}}  goal")
        print("-" * max(96, task_id_width + status_width + meta_width + 12))
        for current_task_id, status, meta, goal in rows:
            print(f"{current_task_id:<{task_id_width}}  {status:<{status_width}}  {meta:<{meta_width}}  {goal}")
        return

    print(f"{'task_id':<{task_id_width}}  {'status':<{status_width}}  goal")
    print("-" * max(80, task_id_width + status_width + 8))
    for current_task_id, status, _meta, goal in rows:
        print(f"{current_task_id:<{task_id_width}}  {status:<{status_width}}  {goal}")


def _graph_sort_key(item: Dict[str, Any]) -> Tuple[float, str]:
    created = item.get("created_at") or item.get("last_seen_at") or item.get("first_seen_at") or 0
    try:
        created_value = float(created)
    except Exception:
        created_value = 0.0
    return (created_value, json.dumps(item, sort_keys=True, default=str))


def _graph_label(value: Any, *, max_width: int = 42) -> str:
    text = _collapse_ws(value)
    if not text:
        return "-"
    if text in {"None", "null", "[]", "{}", "[[]]", "[['fail']]"}:
        return "<non-artifact>"
    text = text.replace("\\", "/")
    if "," in text and not text.startswith("[["):
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) > 1:
            text = ", ".join(Path(part).name for part in parts)
    elif text.startswith("[["):
        return "<compound-plan>"
    elif "/" in text:
        parts = text.split("/")
        if len(parts) >= 3 and parts[0] == "workspace" and parts[1] == "shared":
            text = "shared/" + parts[-1]
        elif len(parts) >= 2 and parts[0] == "workspace":
            text = "workspace/" + parts[-1]
    return _shorten_text(text, max_width=max_width)


def _graph_task_label(value: Any) -> str:
    text = _collapse_ws(value)
    if not text:
        return "-"
    return _shorten_identifier(text, max_width=24)


def _artifact_graph_summary(graph: Dict[str, Any]) -> Tuple[int, int, int]:
    nodes = graph.get("nodes") if isinstance(graph, dict) else []
    edges = graph.get("edges") if isinstance(graph, dict) else []
    events = graph.get("events") if isinstance(graph, dict) else []
    return (
        len(nodes) if isinstance(nodes, list) else 0,
        len(edges) if isinstance(edges, list) else 0,
        len(events) if isinstance(events, list) else 0,
    )


def _print_artifact_graph_summary(graph: Dict[str, Any], *, limit: int = 12) -> None:
    node_count, edge_count, event_count = _artifact_graph_summary(graph)
    print("ZERO Artifact Graph")
    print("")
    print("summary:")
    print(f"  nodes: {node_count}")
    print(f"  edges: {edge_count}")
    print(f"  events: {event_count}")
    print("")

    edges = graph.get("edges") if isinstance(graph, dict) else []
    if not isinstance(edges, list) or not edges:
        print("latest edges: none")
        return

    ordered = sorted((edge for edge in edges if isinstance(edge, dict)), key=_graph_sort_key)
    visible = ordered[-limit:] if limit > 0 and len(ordered) > limit else ordered
    if len(ordered) > len(visible):
        print(f"latest edges: showing {len(visible)} of {len(ordered)}. Use `task graph --all` for all edges.")
    else:
        print("latest edges:")
    print(f"{'from':<32}  {'to':<32}  {'operation':<24}  task")
    print("-" * 106)
    for edge in visible:
        source = _graph_label(edge.get("from"), max_width=32)
        target = _graph_label(edge.get("to"), max_width=32)
        operation = _shorten_text(edge.get("operation") or edge.get("artifact_type") or "-", max_width=24)
        task = _graph_task_label(edge.get("task_id"))
        print(f"{source:<32}  {target:<32}  {operation:<24}  {task}")
    print("")
    print("Use `task graph nodes` for nodes, `task graph edges --all` for all edges, or `task graph json` for raw JSON.")


def _print_artifact_graph_edges(graph: Dict[str, Any], *, limit: Optional[int] = 40) -> None:
    edges = graph.get("edges") if isinstance(graph, dict) else []
    if not isinstance(edges, list) or not edges:
        print("ZERO Artifact Graph edges: none")
        return
    ordered = sorted((edge for edge in edges if isinstance(edge, dict)), key=_graph_sort_key)
    total = len(ordered)
    if limit is not None and limit > 0 and total > limit:
        ordered = ordered[-limit:]
        print(f"ZERO Artifact Graph edges: showing latest {len(ordered)} of {total}. Use `task graph edges --all` for all.")
    else:
        print(f"ZERO Artifact Graph edges: {len(ordered)}")
    print(f"{'from':<36}  {'to':<36}  {'operation':<26}  task")
    print("-" * 114)
    for edge in ordered:
        print(
            f"{_graph_label(edge.get('from'), max_width=36):<36}  "
            f"{_graph_label(edge.get('to'), max_width=36):<36}  "
            f"{_shorten_text(edge.get('operation') or '-', max_width=26):<26}  "
            f"{_graph_task_label(edge.get('task_id'))}"
        )


def _print_artifact_graph_nodes(graph: Dict[str, Any], *, limit: Optional[int] = 40) -> None:
    nodes = graph.get("nodes") if isinstance(graph, dict) else []
    if not isinstance(nodes, list) or not nodes:
        print("ZERO Artifact Graph nodes: none")
        return
    ordered = sorted((node for node in nodes if isinstance(node, dict)), key=_graph_sort_key)
    total = len(ordered)
    if limit is not None and limit > 0 and total > limit:
        ordered = ordered[-limit:]
        print(f"ZERO Artifact Graph nodes: showing latest {len(ordered)} of {total}. Use `task graph nodes --all` for all.")
    else:
        print(f"ZERO Artifact Graph nodes: {len(ordered)}")
    print(f"{'artifact':<44}  {'type':<28}  producer")
    print("-" * 100)
    for node in ordered:
        artifact_label = _graph_label(node.get('artifact'), max_width=44)
        if artifact_label in {"<non-artifact>", "<compound-plan>"}:
            continue
        print(
            f"{artifact_label:<44}  "
            f"{_shorten_text(node.get('artifact_type') or node.get('type') or '-', max_width=28):<28}  "
            f"{_graph_task_label(node.get('producer_task_id'))}"
        )


def _try_handle_fast_task_graph(argv: List[str], repo_root: Path) -> bool:
    if len(argv) < 2 or len(argv) > 4:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False

    action = str(argv[1]).strip().lower()
    if action not in {"graph", "artifact-graph", "artifacts"}:
        return False

    args = [str(item).strip().lower() for item in argv[2:]]
    graph_path = artifact_graph_path(shared_dir(repo_root))
    graph = read_json_file(graph_path)
    if not isinstance(graph, dict):
        graph = {"ok": False, "error": "artifact_graph.json not found"}

    if any(arg in {"json", "--json", "raw", "--raw"} for arg in args):
        _print_json(graph)
        return True

    show_all = any(arg == "--all" for arg in args)
    mode = next((arg for arg in args if arg not in {"--all"}), "summary")
    limit: Optional[int] = None if show_all else 40

    if mode in {"nodes", "node"}:
        _print_artifact_graph_nodes(graph, limit=limit)
        return True
    if mode in {"edges", "edge"}:
        _print_artifact_graph_edges(graph, limit=limit)
        return True
    if mode in {"summary", "text", ""}:
        _print_artifact_graph_summary(graph, limit=12 if not show_all else 10_000_000)
        return True

    print("Unknown task graph mode. Use `task graph`, `task graph edges`, `task graph nodes`, or `task graph json`.")
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



def _try_handle_fast_task_mutation_smoke(argv: List[str], repo_root: Path) -> bool:
    if len(argv) not in {2, 3}:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() not in {"mutation-smoke", "controlled-mutation-smoke", "mutation-probe"}:
        return False

    target_path = str(argv[2]).strip() if len(argv) == 3 else "core/runtime/thin_runtime_bridge.py"
    stamp = int(time.time() * 1000)
    task_name = f"task_{stamp}_mutation_probe"
    task = _new_task(
        task_name,
        f"controlled mutation probe for {target_path}",
    )
    task["type"] = "controlled_mutation"
    task["target_path"] = target_path
    task["requires_review_before_real_source_edit"] = True

    tasks = read_tasks_index(repo_root)
    tasks.append(task)
    write_tasks_index(repo_root, tasks)

    _print_json(
        {
            "ok": True,
            "mode": "controlled_mutation_smoke_v1",
            "created_count": 1,
            "task_id": task_name,
            "target_path": target_path,
            "message": "Created controlled mutation probe task. Run `python app.py task drain`.",
        }
    )
    return True



def _try_handle_fast_task_source_mutation_smoke(argv: List[str], repo_root: Path) -> bool:
    if len(argv) not in {2, 3}:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() not in {"source-mutation-smoke", "controlled-source-mutation", "source-mutation"}:
        return False

    target_path = str(argv[2]).strip() if len(argv) == 3 else "workspace/shared/controlled_source_mutation_target.py"
    target = Path(target_path.replace("\\", "/"))
    if not target.is_absolute():
        target = repo_root / target
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('print("controlled source mutation target")\n', encoding="utf-8")

    stamp = int(time.time() * 1000)
    task_name = f"task_{stamp}_source_mutation"
    task = _new_task(
        task_name,
        f"controlled source mutation for {target_path}",
    )
    task["type"] = "controlled_source_mutation"
    task["target_path"] = target_path
    task["requires_review_before_real_source_edit"] = False
    task["controlled_source_mutation_v2"] = True

    tasks = read_tasks_index(repo_root)
    tasks.append(task)
    write_tasks_index(repo_root, tasks)

    _print_json(
        {
            "ok": True,
            "mode": "controlled_source_mutation_smoke_v2",
            "created_count": 1,
            "task_id": task_name,
            "target_path": target_path,
            "message": "Created controlled source mutation task. Run `python app.py task drain`.",
        }
    )
    return True



def _try_handle_fast_task_mutation_transaction_smoke(argv: List[str], repo_root: Path) -> bool:
    if len(argv) not in {2, 3, 4}:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() not in {"mutation-transaction-smoke", "transaction-mutation-smoke", "mutation-seal"}:
        return False

    target_path = str(argv[2]).strip() if len(argv) >= 3 else "workspace/shared/controlled_mutation_transaction_target.py"
    force_failure = len(argv) == 4 and str(argv[3]).strip().lower() in {"fail", "force-fail", "--fail"}

    target = Path(target_path.replace("\\", "/"))
    if not target.is_absolute():
        target = repo_root / target
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('print("controlled mutation transaction target")\n', encoding="utf-8")

    stamp = int(time.time() * 1000)
    task_name = f"task_{stamp}_mutation_transaction"
    task = _new_task(
        task_name,
        f"controlled mutation transaction for {target_path}",
    )
    task["type"] = "controlled_mutation_transaction"
    task["target_path"] = target_path
    task["force_verification_failure"] = force_failure
    task["controlled_mutation_transaction_seal_v1"] = True

    tasks = read_tasks_index(repo_root)
    tasks.append(task)
    write_tasks_index(repo_root, tasks)

    _print_json(
        {
            "ok": True,
            "mode": "controlled_mutation_transaction_smoke_v1",
            "created_count": 1,
            "task_id": task_name,
            "target_path": target_path,
            "force_verification_failure": force_failure,
            "message": "Created controlled mutation transaction task. Run `python app.py task drain`.",
        }
    )
    return True



def _try_handle_fast_task_engineering_batch_smoke(argv: List[str], repo_root: Path) -> bool:
    if len(argv) not in {2, 3, 4}:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() not in {"engineering-batch-smoke", "transaction-batch-smoke", "batch-mutation-smoke"}:
        return False

    target_arg = str(argv[2]).strip() if len(argv) >= 3 else ""
    force_failure = len(argv) == 4 and str(argv[3]).strip().lower() in {"fail", "force-fail", "--fail"}

    if target_arg:
        targets = [part.strip() for part in target_arg.split(",") if part.strip()]
    else:
        targets = [
            "workspace/shared/engineering_batch_target_a.py",
            "workspace/shared/engineering_batch_target_b.py",
        ]

    for index, target_path in enumerate(targets, start=1):
        target = Path(target_path.replace("\\", "/"))
        if not target.is_absolute():
            target = repo_root / target
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f'print("engineering batch target {index}")\n', encoding="utf-8")

    stamp = int(time.time() * 1000)
    task_name = f"task_{stamp}_engineering_batch"
    task = _new_task(
        task_name,
        "governed engineering transaction batch for " + ",".join(targets),
    )
    task["type"] = "governed_engineering_batch"
    task["targets"] = targets
    task["force_verification_failure"] = force_failure
    task["governed_engineering_transaction_batch_v1"] = True

    tasks = read_tasks_index(repo_root)
    tasks.append(task)
    write_tasks_index(repo_root, tasks)

    _print_json(
        {
            "ok": True,
            "mode": "governed_engineering_transaction_batch_smoke_v1",
            "created_count": 1,
            "task_id": task_name,
            "targets": targets,
            "force_verification_failure": force_failure,
            "message": "Created governed engineering transaction batch task. Run `python app.py task drain`.",
        }
    )
    return True



def _try_handle_fast_task_runtime_plan_smoke(argv: List[str], repo_root: Path) -> bool:
    if len(argv) not in {2, 3, 4}:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() not in {"runtime-plan-smoke", "mutation-plan-smoke", "plan-graph-smoke"}:
        return False

    target_arg = str(argv[2]).strip() if len(argv) >= 3 else ""
    force_failure = len(argv) == 4 and str(argv[3]).strip().lower() in {"fail", "force-fail", "--fail"}

    if target_arg:
        targets = [part.strip() for part in target_arg.split(",") if part.strip()]
    else:
        targets = [
            "workspace/shared/runtime_plan_target_a.py",
            "workspace/shared/runtime_plan_target_b.py",
        ]

    for index, target_path in enumerate(targets, start=1):
        target = Path(target_path.replace("\\", "/"))
        if not target.is_absolute():
            target = repo_root / target
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f'print("runtime plan target {index}")\n', encoding="utf-8")

    stamp = int(time.time() * 1000)
    task_name = f"task_{stamp}_runtime_plan"
    task = _new_task(
        task_name,
        "runtime mutation plan graph for " + ",".join(targets),
    )
    task["type"] = "runtime_mutation_plan"
    task["targets"] = targets
    task["force_verification_failure"] = force_failure
    task["runtime_mutation_plan_graph_v1"] = True

    tasks = read_tasks_index(repo_root)
    tasks.append(task)
    write_tasks_index(repo_root, tasks)

    _print_json(
        {
            "ok": True,
            "mode": "runtime_mutation_plan_graph_smoke_v1",
            "created_count": 1,
            "task_id": task_name,
            "targets": targets,
            "force_verification_failure": force_failure,
            "message": "Created runtime mutation plan graph task. Run `python app.py task drain`.",
        }
    )
    return True



def _try_handle_fast_task_runtime_session_smoke(argv: List[str], repo_root: Path) -> bool:
    if len(argv) not in {2, 3, 4}:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() not in {"runtime-session-smoke", "session-smoke", "long-chain-smoke"}:
        return False

    target_arg = str(argv[2]).strip() if len(argv) >= 3 else ""
    fail_plan_index = 0
    if len(argv) == 4:
        raw_fail = str(argv[3]).strip().lower()
        if raw_fail in {"fail", "force-fail", "--fail"}:
            fail_plan_index = 2
        else:
            try:
                fail_plan_index = int(raw_fail)
            except Exception:
                fail_plan_index = 0

    if target_arg:
        groups = []
        for group_text in target_arg.split(";"):
            group = [part.strip() for part in group_text.split(",") if part.strip()]
            if group:
                groups.append(group)
    else:
        groups = [
            [
                "workspace/shared/runtime_session_plan_a1.py",
                "workspace/shared/runtime_session_plan_a2.py",
            ],
            [
                "workspace/shared/runtime_session_plan_b1.py",
                "workspace/shared/runtime_session_plan_b2.py",
            ],
        ]

    for group_index, group in enumerate(groups, start=1):
        for target_index, target_path in enumerate(group, start=1):
            target = Path(target_path.replace("\\", "/"))
            if not target.is_absolute():
                target = repo_root / target
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f'print("runtime session target {group_index}-{target_index}")\n', encoding="utf-8")

    stamp = int(time.time() * 1000)
    task_name = f"task_{stamp}_runtime_session"
    task = _new_task(
        task_name,
        "persistent runtime session for " + str(groups),
    )
    task["type"] = "persistent_runtime_session"
    task["target_groups"] = groups
    task["fail_plan_index"] = fail_plan_index
    task["persistent_runtime_session_v1"] = True

    tasks = read_tasks_index(repo_root)
    tasks.append(task)
    write_tasks_index(repo_root, tasks)

    _print_json(
        {
            "ok": True,
            "mode": "persistent_runtime_session_smoke_v1",
            "created_count": 1,
            "task_id": task_name,
            "target_groups": groups,
            "fail_plan_index": fail_plan_index,
            "message": "Created persistent runtime session task. Run `python app.py task drain`.",
        }
    )
    return True



def _try_handle_fast_task_runtime_session_resume(argv: List[str], repo_root: Path) -> bool:
    if len(argv) not in {2, 3}:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() not in {"runtime-session-resume", "session-resume", "resume-session"}:
        return False

    source_session_id = str(argv[2]).strip() if len(argv) == 3 else ""
    stamp = int(time.time() * 1000)
    task_name = f"task_{stamp}_session_resume"
    task = _new_task(
        task_name,
        "runtime session resume" + (f" for {source_session_id}" if source_session_id else ""),
    )
    task["type"] = "runtime_session_resume"
    if source_session_id:
        task["source_session_id"] = source_session_id
    task["runtime_session_resume_v1"] = True

    tasks = read_tasks_index(repo_root)
    tasks.append(task)
    write_tasks_index(repo_root, tasks)

    _print_json(
        {
            "ok": True,
            "mode": "runtime_session_resume_v1",
            "created_count": 1,
            "task_id": task_name,
            "source_session_id": source_session_id,
            "message": "Created runtime session resume task. Run `python app.py task drain`.",
        }
    )
    return True



def _try_handle_fast_task_recovery_finalization(argv: List[str], repo_root: Path) -> bool:
    if len(argv) not in {2, 3, 4}:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() not in {"runtime-session-finalize", "recovery-finalize", "session-finalize"}:
        return False

    source_session_id = str(argv[2]).strip() if len(argv) >= 3 else ""
    max_resume_depth = 2
    if len(argv) == 4:
        try:
            max_resume_depth = int(str(argv[3]).strip())
        except Exception:
            max_resume_depth = 2

    stamp = int(time.time() * 1000)
    task_name = f"task_{stamp}_recovery_finalization"
    task = _new_task(
        task_name,
        "runtime session recovery finalization" + (f" for {source_session_id}" if source_session_id else ""),
    )
    task["type"] = "runtime_session_recovery_finalization"
    if source_session_id:
        task["source_session_id"] = source_session_id
    task["max_resume_depth"] = max_resume_depth
    task["runtime_session_recovery_finalization_v1"] = True

    tasks = read_tasks_index(repo_root)
    tasks.append(task)
    write_tasks_index(repo_root, tasks)

    _print_json(
        {
            "ok": True,
            "mode": "runtime_session_recovery_finalization_v1",
            "created_count": 1,
            "task_id": task_name,
            "source_session_id": source_session_id,
            "max_resume_depth": max_resume_depth,
            "message": "Created runtime session recovery finalization task. Run `python app.py task drain`.",
        }
    )
    return True



def _try_handle_fast_task_runtime_supervisor(argv: List[str], repo_root: Path) -> bool:
    if len(argv) not in {2, 3, 4}:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() not in {"runtime-supervisor-smoke", "runtime-supervisor-run", "runtime-watchdog"}:
        return False

    stale_after_seconds = 900
    max_retry_depth = 2
    if len(argv) >= 3:
        try:
            stale_after_seconds = int(str(argv[2]).strip())
        except Exception:
            stale_after_seconds = 900
    if len(argv) == 4:
        try:
            max_retry_depth = int(str(argv[3]).strip())
        except Exception:
            max_retry_depth = 2

    stamp = int(time.time() * 1000)
    task_name = f"task_{stamp}_runtime_supervisor"
    task = _new_task(task_name, "autonomous runtime supervisor scan")
    task["type"] = "runtime_supervisor"
    task["stale_after_seconds"] = stale_after_seconds
    task["max_retry_depth"] = max_retry_depth
    task["runtime_supervisor_v1"] = True

    tasks = read_tasks_index(repo_root)
    tasks.append(task)
    write_tasks_index(repo_root, tasks)

    _print_json(
        {
            "ok": True,
            "mode": "runtime_supervisor_smoke_v1",
            "created_count": 1,
            "task_id": task_name,
            "stale_after_seconds": stale_after_seconds,
            "max_retry_depth": max_retry_depth,
            "message": "Created runtime supervisor task. Run `python app.py task drain`.",
        }
    )
    return True


def _try_handle_fast_task_list(argv: List[str], repo_root: Path) -> bool:
    if len(argv) < 2:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() != "list":
        return False

    options = [str(item).strip() for item in argv[2:] if str(item).strip()]
    verbose = False
    raw = False
    limit: Optional[int] = 40

    i = 0
    while i < len(options):
        option = options[i]
        lowered = option.lower()
        if lowered in {"--verbose", "-v", "verbose"}:
            verbose = True
        elif lowered in {"--raw", "--json", "json"}:
            raw = True
        elif lowered in {"--all", "all"}:
            limit = None
        elif lowered.startswith("--limit="):
            try:
                limit = max(1, int(lowered.split("=", 1)[1]))
            except Exception:
                limit = 40
        elif lowered in {"--limit", "-n"} and i + 1 < len(options):
            try:
                limit = max(1, int(options[i + 1]))
            except Exception:
                limit = 40
            i += 1
        else:
            return False
        i += 1

    _print_task_table(read_tasks_index(repo_root), verbose=verbose, raw=raw, limit=limit)
    return True



def _is_active_queued_status(status: str) -> bool:
    return str(status or "").strip().lower() in {"queued", "ready", "retry", "retrying"}


def _is_stale_queued_task(task: Dict[str, Any]) -> bool:
    if not isinstance(task, dict):
        return False
    if _queued_invalid_reason(task):
        return False
    if not _is_active_queued_status(_queued_status(task)):
        return False
    # Fast CLI tasks are considered runnable by the fast selector, so they are
    # not stale merely because they are old.  Non-fast queued records are
    # scheduler/runtime-owned and should be inspected before cleanup.
    if task.get("fast_cli_path") is True:
        return False
    return True


def _task_audit_record(task: Dict[str, Any], *, reason: str = "") -> Dict[str, Any]:
    return {
        "task_id": task_id(task),
        "status": task_status(task),
        "display_status": _display_task_status(task),
        "goal": _shorten_text(task_goal(task), max_width=120),
        "created_at": task.get("created_at"),
        "fast_cli_path": task.get("fast_cli_path"),
        "reason": reason,
    }


def _task_inventory_audit(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    safe_tasks = [task for task in tasks if isinstance(task, dict)]
    status_counts: Dict[str, int] = {}
    for task in safe_tasks:
        display_status = _display_task_status(task)
        status_counts[display_status] = status_counts.get(display_status, 0) + 1

    invalid_tasks = [
        _task_audit_record(task, reason=_queued_invalid_reason(task))
        for task in safe_tasks
        if _queued_invalid_reason(task)
    ]
    stale_tasks = [
        _task_audit_record(task, reason="non-fast queued task; inspect scheduler/runtime ownership before running or archiving")
        for task in safe_tasks
        if _is_stale_queued_task(task)
    ]
    runnable_fast = [
        _task_audit_record(task, reason="runnable fast queued task")
        for task in safe_tasks
        if _is_fast_runnable_task(task)
    ]

    recommendations: List[str] = []
    if invalid_tasks:
        recommendations.append(f"archive {len(invalid_tasks)} invalid queued task(s)")
    if stale_tasks:
        recommendations.append(f"inspect {len(stale_tasks)} stale/non-fast queued task(s)")
    if not recommendations:
        recommendations.append("task inventory has no queued_invalid or stale queued records")

    return {
        "ok": True,
        "mode": "task_inventory_audit_v1",
        "total_count": len(safe_tasks),
        "status_counts": status_counts,
        "queued_invalid_count": len(invalid_tasks),
        "stale_queued_count": len(stale_tasks),
        "runnable_fast_queued_count": len(runnable_fast),
        "queued_invalid_tasks": invalid_tasks,
        "stale_queued_tasks": stale_tasks,
        "runnable_fast_queued_tasks": runnable_fast,
        "recommendations": recommendations,
    }


def _print_task_audit(payload: Dict[str, Any]) -> None:
    print("ZERO Task Inventory Audit")
    print("")
    print(f"total: {payload.get('total_count', 0)}")
    print("status_counts:")
    counts = payload.get("status_counts")
    if isinstance(counts, dict):
        for status in sorted(counts):
            print(f"  {status}: {counts[status]}")
    print(f"queued_invalid: {payload.get('queued_invalid_count', 0)}")
    print(f"stale_queued: {payload.get('stale_queued_count', 0)}")
    print(f"runnable_fast_queued: {payload.get('runnable_fast_queued_count', 0)}")

    invalid_tasks = payload.get("queued_invalid_tasks")
    if isinstance(invalid_tasks, list) and invalid_tasks:
        print("")
        print("queued_invalid:")
        for task in invalid_tasks[:20]:
            print(f"- {task.get('task_id')}: {task.get('reason')}")

    stale_tasks = payload.get("stale_queued_tasks")
    if isinstance(stale_tasks, list) and stale_tasks:
        print("")
        print("stale/non-fast queued:")
        for task in stale_tasks[:20]:
            print(f"- {task.get('task_id')}: {task.get('goal')}")

    recommendations = payload.get("recommendations")
    if isinstance(recommendations, list) and recommendations:
        print("")
        print("recommendations:")
        for item in recommendations:
            print(f"- {item}")

    print("")
    print("Use `task audit --json` for raw details.")
    print("Use `task cleanup --dry-run` before applying archive status changes.")


def _try_handle_fast_task_audit(argv: List[str], repo_root: Path) -> bool:
    if len(argv) < 2:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() not in {"audit", "inventory", "health"}:
        return False

    args = {str(item).strip().lower() for item in argv[2:] if str(item).strip()}
    if not args.issubset({"--json", "json", "--raw", "raw"}):
        return False

    payload = _task_inventory_audit(read_tasks_index(repo_root))
    if args:
        _print_json(payload)
    else:
        _print_task_audit(payload)
    return True


def _cleanup_target_tasks(tasks: List[Dict[str, Any]], *, include_stale: bool = False) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        if _queued_invalid_reason(task):
            targets.append(task)
            continue
        if include_stale and _is_stale_queued_task(task):
            targets.append(task)
    return targets


def _archive_status_for_task(task: Dict[str, Any]) -> str:
    if _queued_invalid_reason(task):
        return "archived_invalid"
    return "archived_stale"


def _task_cleanup_payload(tasks: List[Dict[str, Any]], *, include_stale: bool, apply: bool) -> Dict[str, Any]:
    targets = _cleanup_target_tasks(tasks, include_stale=include_stale)
    return {
        "ok": True,
        "mode": "task_cleanup_v1",
        "apply": apply,
        "include_stale": include_stale,
        "target_count": len(targets),
        "targets": [
            {
                "task_id": task_id(task),
                "from_status": task_status(task),
                "to_status": _archive_status_for_task(task),
                "reason": _queued_invalid_reason(task) or "stale/non-fast queued task",
                "goal": _shorten_text(task_goal(task), max_width=120),
            }
            for task in targets
        ],
        "message": "dry run only; no tasks were changed" if not apply else "archive status changes applied to tasks index",
    }


def _apply_task_cleanup(tasks: List[Dict[str, Any]], *, include_stale: bool) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    updated: List[Dict[str, Any]] = []
    changed_count = 0
    target_ids = {task_id(task) for task in _cleanup_target_tasks(tasks, include_stale=include_stale)}
    for task in tasks:
        if not isinstance(task, dict):
            updated.append(task)
            continue
        current_id = task_id(task)
        if current_id not in target_ids:
            updated.append(task)
            continue
        next_task = dict(task)
        previous_status = task_status(next_task)
        reason = _queued_invalid_reason(next_task) or "stale/non-fast queued task"
        next_task["status"] = _archive_status_for_task(next_task)
        history = next_task.get("history")
        if not isinstance(history, list):
            history = []
        next_task["history"] = list(history) + [next_task["status"]]
        cleanup_meta = dict(next_task.get("cleanup") or {}) if isinstance(next_task.get("cleanup"), dict) else {}
        cleanup_meta.update(
            {
                "archived_by": "task cleanup",
                "archive_reason": reason,
                "previous_status": previous_status,
                "cleanup_schema": "zero.task_cleanup.v1",
            }
        )
        next_task["cleanup"] = cleanup_meta
        updated.append(next_task)
        changed_count += 1

    payload = _task_cleanup_payload(tasks, include_stale=include_stale, apply=True)
    payload["changed_count"] = changed_count
    return updated, payload


def _print_task_cleanup(payload: Dict[str, Any]) -> None:
    print("ZERO Task Cleanup")
    print(f"ok: {str(bool(payload.get('ok'))).lower()}")
    print(f"apply: {str(bool(payload.get('apply'))).lower()}")
    print(f"include_stale: {str(bool(payload.get('include_stale'))).lower()}")
    print(f"target_count: {payload.get('target_count', 0)}")
    changed = payload.get("changed_count")
    if changed is not None:
        print(f"changed_count: {changed}")
    targets = payload.get("targets")
    if isinstance(targets, list) and targets:
        print("targets:")
        for item in targets[:30]:
            print(f"- {item.get('task_id')}: {item.get('from_status')} -> {item.get('to_status')} ({item.get('reason')})")
    message = payload.get("message")
    if message:
        print(f"message: {message}")
    if not payload.get("apply"):
        print("Run `task cleanup --apply` to archive queued_invalid tasks in tasks.json.")
        print("Add `--include-stale` only after reviewing stale/non-fast queued tasks with `task audit`.")


def _try_handle_fast_task_cleanup(argv: List[str], repo_root: Path) -> bool:
    if len(argv) < 2:
        return False
    if str(argv[0]).strip().lower() != "task":
        return False
    if str(argv[1]).strip().lower() not in {"cleanup", "archive-stale"}:
        return False

    args = {str(item).strip().lower() for item in argv[2:] if str(item).strip()}
    allowed = {"--dry-run", "dry-run", "--apply", "apply", "--json", "json", "--raw", "raw", "--include-stale", "include-stale"}
    if not args.issubset(allowed):
        return False

    wants_json = bool(args.intersection({"--json", "json", "--raw", "raw"}))
    apply = bool(args.intersection({"--apply", "apply"}))
    dry_run = bool(args.intersection({"--dry-run", "dry-run"}))
    include_stale = bool(args.intersection({"--include-stale", "include-stale"}))

    if apply and dry_run:
        payload = {
            "ok": False,
            "mode": "task_cleanup_v1",
            "error": "choose either --dry-run or --apply, not both",
        }
        if wants_json:
            _print_json(payload)
        else:
            _print_task_cleanup(payload)
        return True

    tasks = read_tasks_index(repo_root)
    if not isinstance(tasks, list):
        payload = {"ok": False, "mode": "task_cleanup_v1", "error": "tasks index is not a list"}
    elif apply:
        updated, payload = _apply_task_cleanup(tasks, include_stale=include_stale)
        write_tasks_index(repo_root, updated)
    else:
        payload = _task_cleanup_payload(tasks, include_stale=include_stale, apply=False)

    if wants_json:
        _print_json(payload)
    else:
        _print_task_cleanup(payload)
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

    _print_json(
        _run_via_mainline(
            repo_root,
            entrypoint="cli.task_cli.drain",
            runner=lambda: drain_ingestion_tasks(repo_root, max_rounds=max_rounds),
            goal="task drain",
            request={"command": "drain", "max_rounds": max_rounds},
        )
    )
    return True


def _has_legacy_scheduler_runnable_tasks(repo_root: Path) -> bool:
    """Return True when task run should fall through to the full legacy Scheduler.

    The thin task CLI only owns fast-ingestion tasks that it created itself.
    Full runtime tasks created by app_legacy.py/task_repository are persisted in
    workspace/tasks.json too, but they must be executed by the real Scheduler so
    queue rebuild, TaskRunner, AgentLoop, runtime persistence, and resume state
    are exercised.

    Without this guard, `task run` can be swallowed by the fast CLI and return a
    stale manual_ticks/snapshot payload while a submitted scheduler task remains
    queued forever.
    """
    try:
        tasks = read_tasks_index(repo_root)
    except Exception:
        return False

    if not isinstance(tasks, list):
        return False

    runnable_statuses = {
        "queued",
        "ready",
        "retry",
        "retrying",
        "running",
    }

    for task in tasks:
        if not isinstance(task, dict):
            continue

        status = str(task_status(task) or task.get("status") or "").strip().lower()
        if status not in runnable_statuses:
            continue

        # Fast CLI smoke/ingestion tasks mark themselves explicitly.  Those can
        # still be handled here.  Scheduler-created tasks normally do not carry
        # fast_cli_path=True and must fall through to the full runtime path.
        if task.get("fast_cli_path") is True:
            continue

        return True

    return False


def _is_fast_runnable_task(task: Dict[str, Any]) -> bool:
    if not isinstance(task, dict):
        return False
    status = _queued_status(task)
    if status not in {"queued", "ready", "retry", "retrying"}:
        return False
    if _queued_invalid_reason(task):
        return False
    return task.get("fast_cli_path") is True


def _select_fast_runnable_task(tasks: List[Dict[str, Any]], selector: str) -> Optional[Dict[str, Any]]:
    lowered = selector.lower()

    if lowered not in {"latest", "newest", "last", "next", "oldest", "first"}:
        exact = _find_task_by_id(tasks, selector)
        if exact is None:
            return None
        return exact if _is_fast_runnable_task(exact) else None

    candidates = [task for task in tasks if _is_fast_runnable_task(task)]
    if not candidates:
        return None

    if lowered in {"latest", "newest", "last"}:
        return sorted(candidates, key=_task_sort_key)[-1]
    if lowered in {"next", "oldest", "first"}:
        return sorted(candidates, key=_task_sort_key)[0]

    return None


def _reorder_selected_task_first(tasks: List[Dict[str, Any]], selected_task_id: str) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    rest: List[Dict[str, Any]] = []
    for task in tasks:
        if isinstance(task, dict) and task_id(task) == selected_task_id:
            selected.append(task)
        else:
            rest.append(task)
    return selected + rest


def _task_run_wants_json(argv: List[str]) -> bool:
    return any(str(item).strip().lower() in {"--json", "json", "--raw", "raw"} for item in argv[3:])


def _selected_run_artifact(result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    run_result = result.get("result")
    if not isinstance(run_result, dict):
        return {}
    executed = run_result.get("executed_results")
    if not isinstance(executed, list) or not executed:
        return {}
    first = executed[0]
    if not isinstance(first, dict):
        return {}

    artifact = first.get("artifact")
    if isinstance(artifact, dict) and artifact:
        return artifact

    step_execution = first.get("step_executor_artifact_execution")
    if isinstance(step_execution, dict):
        return {
            "artifact_path": step_execution.get("artifact_path"),
            "artifact_type": step_execution.get("artifact_type"),
            "ok": step_execution.get("ok"),
        }
    return {}


def _selected_run_goal(result: Dict[str, Any]) -> str:
    run_result = result.get("result") if isinstance(result, dict) else None
    if isinstance(run_result, dict):
        executed = run_result.get("executed_results")
        if isinstance(executed, list) and executed and isinstance(executed[0], dict):
            goal = executed[0].get("goal")
            if goal:
                return str(goal)
    return ""


def _print_selected_task_run_result(result: Dict[str, Any]) -> None:
    ok = bool(result.get("ok")) if isinstance(result, dict) else False
    selector = result.get("selector") if isinstance(result, dict) else ""
    selected = result.get("selected_task_id") if isinstance(result, dict) else ""

    print("ZERO Task Run")
    print(f"ok: {str(ok).lower()}")
    if selector:
        print(f"selector: {selector}")
    if selected:
        print(f"selected: {selected}")

    if not ok:
        error = result.get("error") if isinstance(result, dict) else "unknown error"
        reason = result.get("reason") if isinstance(result, dict) else ""
        hint = result.get("hint") if isinstance(result, dict) else ""
        skipped_count = result.get("skipped_invalid_queued_count") if isinstance(result, dict) else 0
        print(f"error: {error}")
        if reason:
            print(f"reason: {reason}")
        if skipped_count:
            print(f"skipped_invalid_queued_count: {skipped_count}")
        if hint:
            print(f"hint: {hint}")
        print("Use `task run <selector> --json` for raw details.")
        return

    goal = _selected_run_goal(result)
    if goal:
        print(f"goal: {_shorten_text(goal, max_width=110)}")

    artifact = _selected_run_artifact(result)
    if artifact:
        artifact_path = artifact.get("artifact_path") or artifact.get("output_path") or artifact.get("path")
        artifact_type = artifact.get("artifact_type") or artifact.get("type")
        if artifact_type:
            print(f"artifact_type: {artifact_type}")
        if artifact_path:
            print(f"artifact: {_graph_label(artifact_path, max_width=96)}")

    run_result = result.get("result") if isinstance(result, dict) else None
    if isinstance(run_result, dict):
        executed_count = run_result.get("executed_count")
        blocked_count = run_result.get("blocked_count")
        if executed_count is not None:
            print(f"executed_count: {executed_count}")
        if blocked_count:
            print(f"blocked_count: {blocked_count}")

    print("Use `task run <selector> --json` for raw runtime/evidence details.")


def _run_selected_fast_task(repo_root: Path, selector: str) -> Dict[str, Any]:
    tasks = read_tasks_index(repo_root)
    if not isinstance(tasks, list):
        return {
            "ok": False,
            "mode": "selected_task_run",
            "selector": selector,
            "error": "tasks index is not a list",
        }

    lowered = selector.lower()
    explicit_task_id = lowered not in {"latest", "newest", "last", "next", "oldest", "first"}
    skipped_invalid = _invalid_queued_tasks(tasks)

    if explicit_task_id:
        exact = _find_task_by_id(tasks, selector)
        if exact is None:
            return {
                "ok": False,
                "mode": "selected_task_run",
                "selector": selector,
                "error": "task id not found",
                "hint": "Use `task list` to inspect known tasks.",
            }

        invalid_reason = _queued_invalid_reason(exact)
        if invalid_reason:
            return {
                "ok": False,
                "mode": "selected_task_run",
                "selector": selector,
                "selected_task_id": task_id(exact),
                "error": "task is queued_invalid and cannot be run by task run",
                "reason": invalid_reason,
                "task_status": task_status(exact),
                "hint": "This is a stale/zombie queued task. Inspect result.json/runtime_state.json or recreate the task.",
            }

        if not _is_fast_runnable_task(exact):
            return {
                "ok": False,
                "mode": "selected_task_run",
                "selector": selector,
                "selected_task_id": task_id(exact),
                "error": "task id exists but is not a queued fast task",
                "reason": f"status={_queued_status(exact) or 'unknown'} fast_cli_path={exact.get('fast_cli_path')!r}",
                "hint": "Use the full scheduler/runtime path for non-fast tasks, or recreate it as a fast CLI task.",
            }

    selected = _select_fast_runnable_task(tasks, selector)
    if selected is None:
        return {
            "ok": False,
            "mode": "selected_task_run",
            "selector": selector,
            "error": "no matching queued fast task",
            "hint": "Use `task list` to inspect queued tasks, or create a new fast task before running `task run next` / `task run latest`.",
            "skipped_invalid_queued_count": len(skipped_invalid),
            "skipped_invalid_queued_tasks": [
                {
                    "task_id": task_id(task),
                    "status": task_status(task),
                    "reason": _queued_invalid_reason(task),
                }
                for task in skipped_invalid[:10]
            ],
        }

    selected_task_id = task_id(selected)
    write_tasks_index(repo_root, _reorder_selected_task_first(tasks, selected_task_id))
    result = _run_via_mainline(
        repo_root,
        entrypoint="cli.task_cli.run_selected",
        runner=lambda: run_ingestion_tasks(repo_root, 1),
        goal=selected_task_id,
        request={"command": "run", "selector": selector, "selected_task_id": selected_task_id},
    )
    return {
        "ok": True,
        "mode": "selected_task_run",
        "selector": selector,
        "selected_task_id": selected_task_id,
        "result": result,
        "fast_cli_path": True,
        "legacy_app_booted": False,
        "skipped_invalid_queued_count": len(skipped_invalid),
        "skipped_invalid_queued_tasks": [
            {
                "task_id": task_id(task),
                "status": task_status(task),
                "reason": _queued_invalid_reason(task),
            }
            for task in skipped_invalid[:10]
        ],
    }


def _try_handle_fast_task_run(argv: List[str], repo_root: Path) -> bool:
    selector = _parse_task_run_selector(argv)
    if selector is not None:
        result = _run_selected_fast_task(repo_root, selector)
        if _task_run_wants_json(argv):
            _print_json(result)
        else:
            _print_selected_task_run_result(result)
        return True

    count = _parse_task_run(argv)
    if count is None:
        return False

    if _has_legacy_scheduler_runnable_tasks(repo_root):
        return False

    ingestion_result = _run_via_mainline(
        repo_root,
        entrypoint="cli.task_cli.run",
        runner=lambda: run_ingestion_tasks(repo_root, count),
        goal="task run",
        request={"command": "run", "count": count},
    )
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

    if _try_handle_fast_task_mutation_smoke(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_source_mutation_smoke(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_mutation_transaction_smoke(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_engineering_batch_smoke(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_runtime_plan_smoke(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_runtime_session_smoke(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_runtime_session_resume(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_recovery_finalization(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_runtime_supervisor(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_drain(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_audit(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_cleanup(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_run(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_list(clean_argv, repo_root):
        return True

    return False
