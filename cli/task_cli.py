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
        status = _shorten_text(task_status(task) or "unknown", max_width=14)
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


def _try_handle_fast_task_run(argv: List[str], repo_root: Path) -> bool:
    count = _parse_task_run(argv)
    if count is None:
        return False

    if _has_legacy_scheduler_runnable_tasks(repo_root):
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

    if _try_handle_fast_task_run(clean_argv, repo_root):
        return True

    if _try_handle_fast_task_list(clean_argv, repo_root):
        return True

    return False
