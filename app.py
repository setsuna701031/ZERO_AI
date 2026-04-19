from __future__ import annotations

import copy
import io
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import traceback
from contextlib import redirect_stdout
from typing import Any, Dict, List, Optional, Tuple

from services.system_boot import boot_system


WORKSPACE_DIR = os.environ.get("ZERO_WORKSPACE", "workspace")

TERMINAL_STATUSES = {
    "finished",
    "completed",
    "failed",
    "canceled",
    "cancelled",
}


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def print_help() -> None:
    print("可用指令：")
    print("  /help")
    print("  /health")
    print("  /runtime")
    print("  /doc_summary")
    print("  /doc_action_items")
    print("  list")
    print("  show <task_id>")
    print("  result <task_id>")
    print("  open <task_id> [target]")
    print("  delete <task_id>")
    print("  retry <task_id>")
    print("  rerun <task_id>")
    print("  purge finished")
    print("  purge failed")
    print("  purge all")
    print("  create <goal>")
    print("  submit [task_id]")
    print("  run [count]")
    print("  tick")
    print("  task list")
    print("  task show <task_id>")
    print("  task result <task_id>")
    print("  task open <task_id> [target]")
    print("  task delete <task_id>")
    print("  task retry <task_id>")
    print("  task rerun <task_id>")
    print("  task purge finished")
    print("  task purge failed")
    print("  task purge all")
    print("  task create <goal>")
    print("  task submit [task_id]")
    print("  task run [count]")
    print("  task doc-summary <input> <output>")
    print("  task doc-action-items <input> <output>")
    print("  chat <message>")
    print("  ask <message>")
    print("  doc summary")
    print("  doc action_items")
    print("  health")
    print("  runtime")
    print("  exit / quit")
    print("")
    print("task open target 可用值：")
    print("  result / log / plan / state / trace / dir / artifact")
    print("")
    print("命令列模式：")
    print("  python app.py task list")
    print("  python app.py task show <task_id>")
    print("  python app.py task result <task_id>")
    print("  python app.py task open <task_id>")
    print("  python app.py task open <task_id> result")
    print("  python app.py task open <task_id> log")
    print("  python app.py task open <task_id> dir")
    print("  python app.py task delete <task_id>")
    print("  python app.py task retry <task_id>")
    print("  python app.py task rerun <task_id>")
    print("  python app.py task purge finished")
    print("  python app.py task doc-summary input.txt summary.txt")
    print("  python app.py task doc-action-items input.txt action_items.txt")
    print('  python app.py chat "你好"')
    print('  python app.py ask "幫我建立一個檔案"')
    print("  python app.py doc summary")
    print("  python app.py doc action_items")
    print("  python app.py health")
    print("  python app.py runtime")
    print("")
    print("模型控制：")
    print('  python app.py chat "你好" --model llama3.1:latest')
    print('  python app.py chat "你好" --plugin local_ollama')
    print('  python app.py ask "幫我建立一個檔案" --model llama3.1:latest --plugin local_ollama')


def _get_scheduler(system: Any) -> Any:
    scheduler = getattr(system, "scheduler", None)
    if scheduler is not None:
        return scheduler
    return system


def _get_agent_loop(system: Any) -> Any:
    for attr in ("agent_loop", "loop"):
        value = getattr(system, attr, None)
        if value is not None:
            return value

    if callable(getattr(system, "run", None)):
        return system

    return None


def _get_planner(system: Any) -> Any:
    for owner in (system, _get_scheduler(system), _get_agent_loop(system)):
        if owner is None:
            continue
        planner = getattr(owner, "planner", None)
        if planner is not None:
            return planner
    return None


def _get_step_executor(system: Any) -> Any:
    for owner in (system, _get_scheduler(system), _get_agent_loop(system)):
        if owner is None:
            continue
        for attr in ("step_executor", "executor"):
            value = getattr(owner, attr, None)
            if value is not None:
                return value
    return None


def _list_tasks(system: Any) -> List[Dict[str, Any]]:
    list_fn = getattr(system, "list_tasks", None)
    if callable(list_fn):
        try:
            result = list_fn()
            if isinstance(result, dict):
                tasks = result.get("tasks")
                if isinstance(tasks, list):
                    return tasks
        except Exception:
            pass

    scheduler = _get_scheduler(system)
    repo = getattr(scheduler, "task_repo", None)
    list_repo_fn = getattr(repo, "list_tasks", None)
    if callable(list_repo_fn):
        try:
            tasks = list_repo_fn()
            if isinstance(tasks, list):
                return tasks
        except Exception:
            pass

    return []


def _get_task(system: Any, task_id: str) -> Optional[Dict[str, Any]]:
    get_fn = getattr(system, "get_task", None)
    if callable(get_fn):
        try:
            result = get_fn(task_id)
            if isinstance(result, dict) and isinstance(result.get("task"), dict):
                return result["task"]
            if isinstance(result, dict) and result.get("task_id"):
                return result
        except Exception:
            pass

    scheduler = _get_scheduler(system)
    helper = getattr(scheduler, "_get_task_from_repo", None)
    if callable(helper):
        try:
            task = helper(task_id)
            if isinstance(task, dict):
                return task
        except Exception:
            pass

    for task in _list_tasks(system):
        if not isinstance(task, dict):
            continue
        candidate = str(task.get("task_id") or task.get("task_name") or "").strip()
        if candidate == task_id:
            return copy.deepcopy(task)

    return None


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _single_line(text: Any) -> str:
    value = _safe_str(text)
    if not value:
        return ""
    return " ".join(value.split())


def _truncate_text(text: Any, max_len: int = 80) -> str:
    value = _single_line(text)
    if not value:
        return ""
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."


def _first_nonempty_str(*values: Any) -> str:
    for value in values:
        text = _safe_str(value)
        if text:
            return text
    return ""


def _find_first_value(data: Any, keys: List[str]) -> Any:
    if not isinstance(data, dict):
        return None

    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value

    execution = data.get("execution")
    if isinstance(execution, dict):
        for key in keys:
            value = execution.get(key)
            if value not in (None, "", [], {}):
                return value

        nested_result = execution.get("result")
        if isinstance(nested_result, dict):
            for key in keys:
                value = nested_result.get(key)
                if value not in (None, "", [], {}):
                    return value

    task_block = data.get("task")
    if isinstance(task_block, dict):
        for key in keys:
            value = task_block.get(key)
            if value not in (None, "", [], {}):
                return value

    return None


def _extract_final_answer(task: Dict[str, Any]) -> str:
    value = _find_first_value(task, ["final_answer", "answer", "response", "message", "summary", "result_text", "content"])
    if isinstance(value, str):
        return value.strip()
    return ""


def _extract_goal(task: Dict[str, Any]) -> str:
    return _first_nonempty_str(task.get("goal"), task.get("title"), task.get("prompt"), task.get("query"), task.get("input"))


def _extract_task_id(task: Dict[str, Any]) -> str:
    return _first_nonempty_str(task.get("task_id"), task.get("task_name"), task.get("id"), task.get("name"))


def _extract_status(task: Dict[str, Any]) -> str:
    return _first_nonempty_str(task.get("status"), "unknown")


def _extract_last_error(task: Dict[str, Any]) -> str:
    value = _find_first_value(task, ["last_error", "failure_message", "error"])
    if isinstance(value, str):
        return value.strip()
    return ""


def _extract_blocked_reason(task: Dict[str, Any]) -> str:
    status = _extract_status(task).lower()
    if status != "blocked":
        return ""
    value = _find_first_value(task, ["blocked_reason"])
    if isinstance(value, str):
        return value.strip()
    return ""


def _extract_state_detail(task: Dict[str, Any]) -> str:
    status = _extract_status(task).lower()
    if status == "blocked":
        return _extract_blocked_reason(task)
    if status in {"failed", "error"}:
        return _extract_last_error(task)
    return ""


def _extract_steps_total(task: Dict[str, Any]) -> int:
    raw = task.get("steps_total")
    if isinstance(raw, int):
        return raw
    steps = task.get("steps")
    if isinstance(steps, list):
        return len(steps)
    plan = task.get("plan")
    if isinstance(plan, list):
        return len(plan)
    return 0


def _extract_current_step_index(task: Dict[str, Any]) -> int:
    raw = task.get("current_step_index")
    if isinstance(raw, int):
        return raw
    raw = task.get("step_index")
    if isinstance(raw, int):
        return raw
    return 0


def _extract_current_step_text(task: Dict[str, Any]) -> str:
    status = _extract_status(task).lower()
    if status in {"finished", "completed"}:
        return ""
    value = _find_first_value(task, ["current_step", "current_step_title", "current_step_name", "step_title", "step_name"])
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return _first_nonempty_str(value.get("title"), value.get("name"), value.get("description"), value.get("goal"), value.get("prompt"), value.get("type"))
    steps = task.get("steps")
    idx = _extract_current_step_index(task)
    if isinstance(steps, list) and 0 <= idx < len(steps):
        step = steps[idx]
        if isinstance(step, dict):
            return _first_nonempty_str(step.get("title"), step.get("name"), step.get("description"), step.get("goal"), step.get("prompt"), step.get("type"))
        if isinstance(step, str):
            return step.strip()
    return ""


def _extract_paths(task: Dict[str, Any]) -> Dict[str, str]:
    candidates = {
        "task_dir": ["task_dir", "task_path", "workspace_path", "work_dir", "working_dir", "sandbox_dir"],
        "result_path": ["result_path", "output_path", "artifact_path", "final_output_path", "result_file"],
        "sandbox_path": ["sandbox_path", "sandbox_result_path", "sandbox_output_path"],
        "plan_path": ["plan_path", "plan_file"],
        "runtime_state_path": ["runtime_state_path", "runtime_state_file", "state_path"],
        "execution_log_path": ["execution_log_path", "execution_log_file", "log_path"],
        "trace_path": ["trace_path", "trace_file"],
        "snapshot_path": ["snapshot_path", "snapshot_file"],
    }

    result: Dict[str, str] = {}
    for output_key, keys in candidates.items():
        value = _find_first_value(task, keys)
        if isinstance(value, str) and value.strip():
            result[output_key] = value.strip()

    task_id = _extract_task_id(task)
    if task_id and "task_dir" not in result:
        result["task_dir"] = os.path.join(WORKSPACE_DIR, "tasks", task_id)
    if "result_path" not in result and result.get("task_dir"):
        result["result_path"] = os.path.join(result["task_dir"], "result.json")
    if "plan_path" not in result and result.get("task_dir"):
        result["plan_path"] = os.path.join(result["task_dir"], "plan.json")
    if "runtime_state_path" not in result and result.get("task_dir"):
        result["runtime_state_path"] = os.path.join(result["task_dir"], "runtime_state.json")
    if "execution_log_path" not in result and result.get("task_dir"):
        result["execution_log_path"] = os.path.join(result["task_dir"], "execution_log.json")
    if "trace_path" not in result and result.get("task_dir"):
        result["trace_path"] = os.path.join(result["task_dir"], "trace.json")
    if "snapshot_path" not in result and result.get("task_dir"):
        result["snapshot_path"] = os.path.join(result["task_dir"], "task_snapshot.json")
    return result


def _load_json_file(path: str) -> Optional[Dict[str, Any]]:
    file_path = _safe_str(path)
    if not file_path or not os.path.isfile(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _load_task_snapshot(task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(task, dict):
        return None
    if isinstance(task.get("open_targets"), list) or isinstance(task.get("artifacts"), list):
        return task
    paths = _extract_paths(task)
    snapshot_candidates = [
        _safe_str(task.get("snapshot_file")),
        _safe_str(task.get("snapshot_path")),
        _safe_str(paths.get("snapshot_path")),
        os.path.join(_safe_str(paths.get("task_dir")), "task_snapshot.json") if _safe_str(paths.get("task_dir")) else "",
    ]
    seen = set()
    for path in snapshot_candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        loaded = _load_json_file(path)
        if isinstance(loaded, dict):
            return loaded
    return None


def _merge_task_with_snapshot(task: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(task if isinstance(task, dict) else {})
    snapshot = _load_task_snapshot(task)
    if not isinstance(snapshot, dict):
        return merged
    for key, value in snapshot.items():
        if key not in merged or merged.get(key) in (None, "", [], {}):
            merged[key] = copy.deepcopy(value)
    return merged


def _guess_artifact_scope(path: str) -> str:
    normalized = _safe_str(path).replace("/", "\\").lower()
    shared_root = os.path.abspath(os.path.join(WORKSPACE_DIR, "shared")).replace("/", "\\").lower()
    if normalized.startswith(shared_root):
        return "shared"
    if "\\workspace\\shared\\" in normalized or normalized.endswith("\\workspace\\shared"):
        return "shared"
    return "task"


def _build_artifact_targets(task: Dict[str, Any]) -> List[Dict[str, Any]]:
    merged_task = _merge_task_with_snapshot(task)
    paths = _extract_paths(merged_task)
    targets: List[Dict[str, Any]] = []
    seen_paths = set()

    def add_target(path: Any, name: str = "", kind: str = "", scope: str = "") -> None:
        text = _safe_str(path)
        if not text or text in seen_paths:
            return
        seen_paths.add(text)
        resolved_scope = _safe_str(scope) or _guess_artifact_scope(text)
        targets.append(
            {
                "path": text,
                "name": _safe_str(name) or os.path.basename(text) or text,
                "kind": _safe_str(kind),
                "scope": resolved_scope,
                "exists": os.path.exists(text),
            }
        )

    snapshot_targets = merged_task.get("open_targets")
    if isinstance(snapshot_targets, list):
        for item in snapshot_targets:
            if isinstance(item, dict):
                add_target(
                    item.get("path"),
                    name=_safe_str(item.get("name")),
                    kind=_safe_str(item.get("kind")),
                    scope=_safe_str(item.get("scope")),
                )

    artifacts = merged_task.get("artifacts")
    if isinstance(artifacts, list):
        for item in artifacts:
            if isinstance(item, dict):
                add_target(
                    item.get("path"),
                    name=_safe_str(item.get("name")),
                    kind=_safe_str(item.get("kind")),
                    scope=_safe_str(item.get("scope")),
                )

    add_target(paths.get("result_path"), "result.json", "result", "task")
    add_target(paths.get("execution_log_path"), "execution_log.json", "log", "task")
    add_target(paths.get("plan_path"), "plan.json", "plan", "task")
    add_target(paths.get("runtime_state_path"), "runtime_state.json", "state", "task")
    add_target(paths.get("trace_path"), "trace.json", "trace", "task")
    add_target(paths.get("snapshot_path"), "task_snapshot.json", "snapshot", "task")
    add_target(paths.get("task_dir"), _extract_task_id(merged_task), "dir", "task")
    return targets

def _extract_shared_artifact_paths(task: Dict[str, Any]) -> List[str]:
    shared_paths: List[str] = []
    seen = set()

    for item in _build_artifact_targets(task):
        if not isinstance(item, dict):
            continue
        scope = _safe_str(item.get("scope")).lower()
        path = _safe_str(item.get("path"))
        if scope != "shared" or not path or path in seen:
            continue
        seen.add(path)
        shared_paths.append(path)

    return shared_paths



def _pick_open_target(task: Dict[str, Any], selector: str = "") -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    merged_task = _merge_task_with_snapshot(task)
    paths = _extract_paths(merged_task)
    targets = _build_artifact_targets(merged_task)
    normalized_selector = _safe_str(selector).lower()

    selector_aliases = {
        "result": {"result", "result.json", "output"},
        "log": {"log", "execution_log", "execution_log.json"},
        "plan": {"plan", "plan.json"},
        "state": {"state", "runtime_state", "runtime_state.json"},
        "trace": {"trace", "trace.json"},
        "dir": {"dir", "task_dir", "folder"},
        "artifact": {"artifact", "file", "output_file"},
        "snapshot": {"snapshot", "task_snapshot", "task_snapshot.json"},
    }

    def first_existing(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for item in candidates:
            if bool(item.get("exists")):
                return item
        for item in candidates:
            if _safe_str(item.get("path")):
                return item
        return None

    def sort_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        def rank(item: Dict[str, Any]) -> Tuple[int, int, int, str]:
            scope = _safe_str(item.get("scope")).lower()
            kind = _safe_str(item.get("kind")).lower()
            name = _safe_str(item.get("name")).lower()
            path = _safe_str(item.get("path")).lower()

            scope_rank = 0 if scope == "shared" else 1
            kind_rank = 1
            if kind == "dir":
                kind_rank = 4
            elif kind in {"result", "log", "plan", "state", "trace", "snapshot"}:
                kind_rank = 3
            elif name.endswith((".py", ".txt", ".md", ".csv", ".yaml", ".yml")) or path.endswith((".py", ".txt", ".md", ".csv", ".yaml", ".yml")):
                kind_rank = 0
            elif name.endswith((".json", ".log")) or path.endswith((".json", ".log")):
                kind_rank = 2

            exists_rank = 0 if bool(item.get("exists")) else 1
            return (scope_rank, kind_rank, exists_rank, name or path)

        return sorted(candidates, key=rank)

    if normalized_selector:
        mapping = {
            "result": ("result_path", "result.json", "result", "task"),
            "log": ("execution_log_path", "execution_log.json", "log", "task"),
            "plan": ("plan_path", "plan.json", "plan", "task"),
            "state": ("runtime_state_path", "runtime_state.json", "state", "task"),
            "trace": ("trace_path", "trace.json", "trace", "task"),
            "dir": ("task_dir", _extract_task_id(merged_task), "dir", "task"),
            "snapshot": ("snapshot_path", "task_snapshot.json", "snapshot", "task"),
        }
        for alias, keys in selector_aliases.items():
            if normalized_selector in keys and alias in mapping:
                path_key, name, kind, scope = mapping[alias]
                return first_existing([{"path": paths.get(path_key), "name": name, "kind": kind, "scope": scope, "exists": os.path.exists(_safe_str(paths.get(path_key)))}]), targets

        if normalized_selector in selector_aliases["artifact"]:
            artifact_candidates = []
            for item in targets:
                name = _safe_str(item.get("name")).lower()
                kind = _safe_str(item.get("kind")).lower()
                path = _safe_str(item.get("path")).lower()
                scope = _safe_str(item.get("scope")).lower()
                if scope == "shared":
                    artifact_candidates.append(item)
                    continue
                if kind not in {"result", "log", "plan", "state", "trace", "snapshot", "dir"}:
                    artifact_candidates.append(item)
                    continue
                if name.endswith((".py", ".txt", ".md", ".json", ".csv", ".yaml", ".yml", ".log")) and bool(item.get("exists")):
                    artifact_candidates.append(item)
                    continue
                if path.endswith((".py", ".txt", ".md", ".json", ".csv", ".yaml", ".yml", ".log")) and bool(item.get("exists")):
                    artifact_candidates.append(item)
                    continue
            chosen = first_existing(sort_candidates(artifact_candidates))
            if chosen is not None:
                return chosen, targets

        for item in targets:
            path = _safe_str(item.get("path")).lower()
            name = _safe_str(item.get("name")).lower()
            kind = _safe_str(item.get("kind")).lower()
            if normalized_selector in {path, name, kind} and bool(item.get("exists")):
                return item, targets

    artifact_candidates: List[Dict[str, Any]] = []
    for item in targets:
        name = _safe_str(item.get("name")).lower()
        kind = _safe_str(item.get("kind")).lower()
        path = _safe_str(item.get("path")).lower()
        scope = _safe_str(item.get("scope")).lower()
        if scope == "shared":
            artifact_candidates.append(item)
            continue
        if kind not in {"result", "log", "plan", "state", "trace", "snapshot", "dir"}:
            artifact_candidates.append(item)
            continue
        if name.endswith((".py", ".txt", ".md", ".csv", ".yaml", ".yml")) or path.endswith((".py", ".txt", ".md", ".csv", ".yaml", ".yml")):
            artifact_candidates.append(item)

    chosen = first_existing(sort_candidates(artifact_candidates))
    if chosen is not None:
        return chosen, targets

    for key, name, kind in [("result_path", "result.json", "result"), ("execution_log_path", "execution_log.json", "log"), ("plan_path", "plan.json", "plan"), ("task_dir", _extract_task_id(merged_task), "dir")]:
        chosen = first_existing([{"path": paths.get(key), "name": name, "kind": kind, "scope": "task", "exists": os.path.exists(_safe_str(paths.get(key)))}])
        if chosen is not None:
            return chosen, targets
    return None, targets


def _open_local_path(path: str) -> Tuple[bool, str]:
    target = _safe_str(path)
    if not target:
        return False, "empty path"
    if not os.path.exists(target):
        return False, f"path not found: {target}"
    try:
        if os.name == "nt":
            os.startfile(target)  # type: ignore[attr-defined]
            return True, ""
        if sys.platform == "darwin":
            subprocess.Popen(["open", target])
            return True, ""
        subprocess.Popen(["xdg-open", target])
        return True, ""
    except Exception as e:
        return False, str(e)


def _parse_task_open_args(raw: str) -> Tuple[str, str]:
    text = _safe_str(raw)
    if not text:
        return "", ""
    parts = text.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _format_step_progress(task: Dict[str, Any]) -> str:
    current_idx = _extract_current_step_index(task)
    total = _extract_steps_total(task)
    if total <= 0:
        return "-"
    display_current = current_idx
    status = _extract_status(task).lower()
    if status in TERMINAL_STATUSES and current_idx < total:
        display_current = total
    elif display_current < 0:
        display_current = 0
    return f"{display_current}/{total}"


def _print_task_table(tasks: List[Dict[str, Any]]) -> None:
    if not tasks:
        print("目前沒有 task。")
        return
    rows: List[Dict[str, str]] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task = _merge_task_with_snapshot(task)
        result_summary = _extract_final_answer(task) or _extract_state_detail(task)
        rows.append({"task_id": _extract_task_id(task), "status": _extract_status(task), "step": _format_step_progress(task), "goal": _truncate_text(_extract_goal(task), 26), "result_summary": _truncate_text(result_summary, 42)})
    if not rows:
        print("目前沒有 task。")
        return
    task_id_w = max(len("task_id"), min(24, max(len(r["task_id"]) for r in rows)))
    status_w = max(len("status"), min(12, max(len(r["status"]) for r in rows)))
    step_w = max(len("step"), min(8, max(len(r["step"]) for r in rows)))
    goal_w = max(len("goal"), min(26, max(len(r["goal"]) for r in rows)))
    header = f"{'task_id':<{task_id_w}}  {'status':<{status_w}}  {'step':<{step_w}}  {'goal':<{goal_w}}  result_summary"
    print(header)
    print("-" * max(100, len(header)))
    for row in rows:
        print(f"{row['task_id']:<{task_id_w}}  {row['status']:<{status_w}}  {row['step']:<{step_w}}  {row['goal']:<{goal_w}}  {row['result_summary']}")


def _print_task_summary(task: Dict[str, Any]) -> None:
    task = _merge_task_with_snapshot(task)
    task_id = _extract_task_id(task)
    status = _extract_status(task)
    goal = _extract_goal(task)
    step_progress = _format_step_progress(task)
    current_step_text = _extract_current_step_text(task)
    final_answer = _extract_final_answer(task)
    last_error = _extract_last_error(task)
    blocked_reason = _extract_blocked_reason(task)
    paths = _extract_paths(task)
    shared_artifacts = _extract_shared_artifact_paths(task)
    print(f"task_id: {task_id}")
    print(f"status: {status}")
    print(f"step: {step_progress}")
    if goal:
        print("goal:")
        print(textwrap.indent(goal, "  "))
    if current_step_text:
        print("current_step:")
        print(textwrap.indent(current_step_text, "  "))
    if final_answer:
        print("final_answer:")
        print(textwrap.indent(final_answer, "  "))
    if blocked_reason:
        print("blocked_reason:")
        print(textwrap.indent(blocked_reason, "  "))
    if last_error:
        print("last_error:")
        print(textwrap.indent(last_error, "  "))
    if paths:
        print("paths:")
        for key, value in paths.items():
            print(f"  {key}: {value}")
    if shared_artifacts:
        print("shared_artifacts:")
        for path in shared_artifacts:
            print(f"  - {path}")


def _print_task_result(task: Dict[str, Any]) -> None:
    task = _merge_task_with_snapshot(task)
    task_id = _extract_task_id(task)
    status = _extract_status(task)
    final_answer = _extract_final_answer(task)
    last_error = _extract_last_error(task)
    blocked_reason = _extract_blocked_reason(task)
    paths = _extract_paths(task)
    shared_artifacts = _extract_shared_artifact_paths(task)
    print(f"task_id: {task_id}")
    print(f"status: {status}")
    print("final_answer:")
    if final_answer:
        print(textwrap.indent(final_answer, "  "))
    else:
        print("  <empty>")
    if blocked_reason:
        print("blocked_reason:")
        print(textwrap.indent(blocked_reason, "  "))
    if last_error:
        print("last_error:")
        print(textwrap.indent(last_error, "  "))
    visible_path_keys = ["result_path", "sandbox_path", "task_dir", "plan_path", "runtime_state_path", "execution_log_path", "trace_path", "snapshot_path"]
    any_path = False
    for key in visible_path_keys:
        value = paths.get(key, "").strip()
        if value:
            if not any_path:
                print("paths:")
                any_path = True
            print(f"  {key}: {value}")
    if shared_artifacts:
        print("shared_artifacts:")
        for path in shared_artifacts:
            print(f"  - {path}")


def _create_task(system: Any, goal: str) -> Dict[str, Any]:
    scheduler = _get_scheduler(system)
    create_fn = getattr(scheduler, "create_task", None)
    if callable(create_fn):
        try:
            result = create_fn(goal=goal, priority=0, max_retries=0, retry_delay=0, timeout_ticks=0)
            if isinstance(result, dict):
                return result
            return {"ok": bool(result)}
        except Exception as e:
            return {"ok": False, "error": f"scheduler.create_task failed: {e}"}
    create_fn = getattr(system, "create_task", None)
    if callable(create_fn):
        try:
            result = create_fn(goal)
            if isinstance(result, dict):
                return result
            return {"ok": bool(result)}
        except Exception as e:
            return {"ok": False, "error": f"system.create_task failed: {e}"}
    return {"ok": False, "error": "create_task not available"}


def _submit_existing_task(system: Any, task_id: str) -> Dict[str, Any]:
    scheduler = _get_scheduler(system)
    submit_fn = getattr(scheduler, "submit_existing_task", None)
    if callable(submit_fn):
        try:
            result = submit_fn(task_id)
            if isinstance(result, dict):
                return result
            return {"ok": bool(result), "task_id": task_id}
        except Exception as e:
            return {"ok": False, "error": f"submit_existing_task failed: {e}", "task_id": task_id}
    return {"ok": False, "error": "submit_existing_task not available", "task_id": task_id}


def _spawn_task_from_existing(system: Any, task_id: str, action_name: str) -> Dict[str, Any]:
    old_task = _get_task(system, task_id)
    if not isinstance(old_task, dict):
        return {"ok": False, "error": "source task not found", "source_task_id": task_id, "action": action_name}
    goal = _extract_goal(old_task)
    if not goal:
        return {"ok": False, "error": "source task goal is empty", "source_task_id": task_id, "action": action_name}
    create_result = _create_task(system, goal)
    if not isinstance(create_result, dict) or not create_result.get("ok", False):
        return {"ok": False, "error": "create_task failed", "source_task_id": task_id, "goal": goal, "action": action_name, "create_result": create_result}
    created_task = create_result.get("task", {}) if isinstance(create_result.get("task"), dict) else {}
    new_task_id = _first_nonempty_str(create_result.get("task_id"), create_result.get("task_name"), created_task.get("task_id"), created_task.get("task_name"))
    if not new_task_id:
        return {"ok": False, "error": "created task but no task_id returned", "source_task_id": task_id, "goal": goal, "action": action_name, "create_result": create_result}
    submit_result = _submit_existing_task(system, new_task_id)
    return {"ok": bool(submit_result.get("ok", False)) if isinstance(submit_result, dict) else False, "action": action_name, "source_task_id": task_id, "new_task_id": new_task_id, "goal": goal, "create_result": create_result, "submit_result": submit_result}


def _retry_task(system: Any, task_id: str) -> Dict[str, Any]:
    scheduler = _get_scheduler(system)
    retry_fn = getattr(scheduler, "retry_task", None)
    if callable(retry_fn):
        try:
            result = retry_fn(task_id)
            if isinstance(result, dict):
                return result
            return {"ok": bool(result), "task_id": task_id}
        except Exception as e:
            return {"ok": False, "error": f"retry_task failed: {e}", "task_id": task_id}
    return {"ok": False, "error": "retry_task not available", "task_id": task_id}


def _rerun_task(system: Any, task_id: str) -> Dict[str, Any]:
    return _spawn_task_from_existing(system, task_id, action_name="task_rerun")


def _run_once(system: Any) -> Dict[str, Any]:
    scheduler = _get_scheduler(system)
    run_fn = getattr(scheduler, "run_once", None)
    if callable(run_fn):
        try:
            result = run_fn()
            if isinstance(result, dict):
                return result
            return {"ok": bool(result)}
        except Exception as e:
            return {"ok": False, "error": f"run_once failed: {e}"}
    tick_fn = getattr(scheduler, "tick", None)
    if callable(tick_fn):
        try:
            result = tick_fn()
            if isinstance(result, dict):
                return result
            return {"ok": bool(result)}
        except Exception as e:
            return {"ok": False, "error": f"tick failed: {e}"}
    return {"ok": False, "error": "run method not available"}


def _delete_task_from_repo(system: Any, task_id: str) -> Dict[str, Any]:
    scheduler = _get_scheduler(system)
    repo = getattr(scheduler, "task_repo", None)
    removed = False
    errors: List[str] = []
    if repo is not None:
        for method_name in ("delete_task", "remove_task", "delete", "remove"):
            method = getattr(repo, method_name, None)
            if callable(method):
                try:
                    result = method(task_id)
                    removed = bool(result) or removed
                    if removed:
                        break
                except Exception as e:
                    errors.append(f"{method_name}: {e}")
        if not removed:
            for attr_name in ("tasks", "_tasks"):
                container = getattr(repo, attr_name, None)
                if isinstance(container, dict) and task_id in container:
                    try:
                        del container[task_id]
                        removed = True
                        save_fn = getattr(repo, "save", None)
                        if callable(save_fn):
                            try:
                                save_fn()
                            except Exception:
                                pass
                        break
                    except Exception as e:
                        errors.append(f"dict delete: {e}")
    task_dir = os.path.join(WORKSPACE_DIR, "tasks", task_id)
    if os.path.isdir(task_dir):
        try:
            shutil.rmtree(task_dir)
        except Exception as e:
            errors.append(f"remove task dir: {e}")
    return {"ok": removed, "task_id": task_id, "errors": errors}


def _purge_tasks(system: Any, mode: str) -> Dict[str, Any]:
    tasks = _list_tasks(system)
    deleted: List[str] = []
    failed: List[Dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = _extract_task_id(task)
        status = _extract_status(task).lower()
        should_delete = mode == "all" or (mode == "finished" and status in {"finished", "completed", "done", "success"}) or (mode == "failed" and status in {"failed", "error"})
        if not should_delete or not task_id:
            continue
        result = _delete_task_from_repo(system, task_id)
        if result.get("ok"):
            deleted.append(task_id)
        else:
            failed.append({"task_id": task_id, "errors": result.get("errors", [])})
    return {"ok": True, "mode": mode, "deleted_count": len(deleted), "deleted": deleted, "failed_count": len(failed), "failed": failed}


def _normalize_cli_command(text: str) -> Optional[str]:
    stripped = str(text or "").strip()
    if not stripped:
        return None
    if stripped.startswith("/"):
        return stripped
    lowered = stripped.lower()
    mapping = {
        "help": "/help",
        "health": "/health",
        "runtime": "/runtime",
        "list": "/task_list",
        "tick": "/task_run 1",
        "run": "/task_run 1",
        "doc summary": "/doc_summary",
    }
    if lowered in mapping:
        return mapping[lowered]
    if lowered in {"doc action_items", "doc action-items", "doc actionitems"}:
        return "/doc_action_items"
    prefixes = [
        ("create ", "/task_create "),
        ("new ", "/task_create "),
        ("submit ", "/task_submit "),
        ("show ", "/task_show "),
        ("result ", "/task_result "),
        ("open ", "/task_open "),
        ("delete ", "/task_delete "),
        ("retry ", "/task_retry "),
        ("rerun ", "/task_rerun "),
        ("purge ", "/task_purge "),
        ("task doc-summary ", "/task_doc_summary "),
        ("task doc-action-items ", "/task_doc_action_items "),
        ("task doc-action_items ", "/task_doc_action_items "),
        ("task doc action-items ", "/task_doc_action_items "),
        ("task doc action_items ", "/task_doc_action_items "),
        ("task doc summary ", "/task_doc_summary "),
    ]
    for prefix, target in prefixes:
        if lowered.startswith(prefix):
            return target + stripped[len(prefix):].strip()
    if lowered.startswith("chat ") or lowered.startswith("ask "):
        return stripped
    if lowered == "submit":
        return "/task_submit"
    if lowered == "task list":
        return "/task_list"
    if lowered == "task run":
        return "/task_run 1"
    task_prefixes = [
        ("task run ", "/task_run "),
        ("task create ", "/task_create "),
        ("task new ", "/task_create "),
        ("task submit ", "/task_submit "),
        ("task show ", "/task_show "),
        ("task result ", "/task_result "),
        ("task open ", "/task_open "),
        ("task delete ", "/task_delete "),
        ("task retry ", "/task_retry "),
        ("task rerun ", "/task_rerun "),
        ("task purge ", "/task_purge "),
    ]
    for prefix, target in task_prefixes:
        if lowered.startswith(prefix):
            return target + stripped[len(prefix):].strip()
    if lowered == "task submit":
        return "/task_submit"
    return None


def _extract_agent_output(result: Any) -> Optional[str]:
    if isinstance(result, str):
        text = result.strip()
        return text or None
    if not isinstance(result, dict):
        return None
    for key in ("final_answer", "answer", "response", "message", "summary"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    execution = result.get("execution")
    if isinstance(execution, dict):
        for key in ("final_answer", "answer", "response", "message", "summary"):
            value = execution.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        nested_result = execution.get("result")
        if isinstance(nested_result, dict):
            for key in ("final_answer", "answer", "response", "message", "summary", "content"):
                value = nested_result.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return None


def _build_runtime_info(system: Any) -> Dict[str, Any]:
    scheduler = _get_scheduler(system)
    agent = _get_agent_loop(system)
    llm_client = getattr(agent, "llm_client", None) if agent is not None else None
    if llm_client is None:
        llm_client = getattr(system, "llm_client", None)
    if llm_client is None and scheduler is not None:
        llm_client = getattr(scheduler, "llm_client", None)
    runtime_info: Dict[str, Any] = {"ok": True, "app": "ZERO Task OS", "workspace_dir": WORKSPACE_DIR, "has_scheduler": scheduler is not None, "has_agent_loop": agent is not None, "llm": {"plugin_name": "", "provider": "", "base_url": "", "model": "", "coder_model": "", "timeout": None}}
    get_runtime_info_fn = getattr(llm_client, "get_runtime_info", None)
    if callable(get_runtime_info_fn):
        try:
            runtime_info["llm"] = get_runtime_info_fn()
            return runtime_info
        except Exception as e:
            runtime_info["llm_error"] = f"get_runtime_info failed: {e}"
            return runtime_info
    runtime_info["llm"] = {"plugin_name": _safe_str(getattr(llm_client, "plugin_name", "")), "provider": _safe_str(getattr(llm_client, "provider", "")), "base_url": _safe_str(getattr(llm_client, "base_url", "")), "model": _safe_str(getattr(llm_client, "model", "")), "coder_model": _safe_str(getattr(llm_client, "coder_model", "")), "timeout": getattr(llm_client, "timeout", None)}
    return runtime_info


def _build_health_info(system: Any) -> Dict[str, Any]:
    health_fn = getattr(system, "health", None)
    base_health: Dict[str, Any] = {}
    if callable(health_fn):
        try:
            raw = health_fn()
            if isinstance(raw, dict):
                base_health = raw
        except Exception as e:
            base_health = {"ok": False, "error": f"health() failed: {e}"}
    runtime = _build_runtime_info(system)
    merged = {"ok": True, "workspace_dir": WORKSPACE_DIR, "runtime": runtime}
    merged.update(base_health)
    return merged


def _extract_all_file_paths_from_text(text: str) -> List[str]:
    if not text:
        return []

    results: List[str] = []
    pattern = r"\b([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b"
    for match in re.finditer(pattern, text):
        value = str(match.group(1)).strip()
        if value and value not in results:
            results.append(value)
    return results


def _extract_arrow_paths_from_text(text: str) -> Optional[Tuple[str, str]]:
    stripped = _safe_str(text)
    if not stripped:
        return None

    match = re.search(
        r"([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\s*->\s*([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))",
        stripped,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    source_path = _safe_str(match.group(1))
    output_path = _safe_str(match.group(2))
    if not source_path or not output_path:
        return None
    return source_path, output_path


def _extract_document_source_path_from_text(text: str, all_paths: List[str]) -> str:
    stripped = _safe_str(text)

    patterns = [
        r"\bfrom\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        r"\bread\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        r"\bsummari[sz]e\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        r"\bsummary\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        r"\bextract\s+action\s+items\s+from\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, stripped, flags=re.IGNORECASE)
        if match:
            value = _safe_str(match.group(1))
            if value:
                return value

    arrow = _extract_arrow_paths_from_text(stripped)
    if arrow is not None:
        return arrow[0]

    if all_paths:
        return all_paths[0]

    return ""


def _extract_document_output_path_from_text(text: str, all_paths: List[str]) -> str:
    stripped = _safe_str(text)

    patterns = [
        r"\binto\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        r"\bto\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        r"\bwrite\s+.+?\s+to\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        r"\boutput\s+to\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, stripped, flags=re.IGNORECASE)
        if match:
            value = _safe_str(match.group(1))
            if value:
                return value

    arrow = _extract_arrow_paths_from_text(stripped)
    if arrow is not None:
        return arrow[1]

    if len(all_paths) >= 2:
        return all_paths[-1]

    return ""


def _extract_document_task_payload(text: str) -> Optional[Dict[str, str]]:
    stripped = _safe_str(text)
    if not stripped:
        return None

    lowered = stripped.lower()
    all_paths = _extract_all_file_paths_from_text(stripped)

    action_keywords = [
        "action item",
        "action items",
        "extract action items",
        "todo",
        "to-do",
        "行動項目",
        "待辦事項",
    ]
    summary_keywords = [
        "summary",
        "summarize",
        "summarise",
        "摘要",
        "總結",
    ]

    wants_action_items = any(keyword in lowered for keyword in action_keywords)
    wants_summary = any(keyword in lowered for keyword in summary_keywords)

    if not wants_action_items and not wants_summary:
        output_hint = _extract_document_output_path_from_text(stripped, all_paths).lower()
        if "action_items" in output_hint or "action-items" in output_hint or "actionitems" in output_hint:
            wants_action_items = True
        elif "summary" in output_hint:
            wants_summary = True

    if not wants_action_items and not wants_summary:
        return None

    input_file = _extract_document_source_path_from_text(stripped, all_paths) or "input.txt"

    if wants_action_items:
        output_file = _extract_document_output_path_from_text(stripped, all_paths) or "action_items.txt"
        return {
            "task_type": "document",
            "mode": "action_items",
            "input_file": input_file,
            "output_file": output_file,
        }

    output_file = _extract_document_output_path_from_text(stripped, all_paths) or "summary.txt"
    return {
        "task_type": "document",
        "mode": "summary",
        "input_file": input_file,
        "output_file": output_file,
    }


def _build_direct_flow_context(text: str) -> Dict[str, Any]:
    context: Dict[str, Any] = {"user_input": text}
    payload = _extract_document_task_payload(text)
    if payload:
        context.update(payload)
    return context


def _build_doc_task_goal(mode: str, input_file: str, output_file: str) -> str:
    mode_text = _safe_str(mode).lower()
    input_path = _safe_str(input_file)
    output_path = _safe_str(output_file)

    if not input_path or not output_path:
        return ""

    if mode_text == "summary":
        return f"summarize {input_path} into {output_path}"

    if mode_text in {"action_items", "action-items", "actionitems"}:
        return f"read {input_path} and extract action items into {output_path}"

    return ""


def _parse_doc_task_args(raw: str) -> Tuple[str, str]:
    text = _safe_str(raw)
    if not text:
        return "", ""
    parts = text.split()
    if len(parts) < 2:
        return "", ""
    return parts[0].strip(), parts[1].strip()


def _should_use_direct_step_flow(text: str) -> bool:
    stripped = _safe_str(text)
    if not stripped:
        return False

    lowered = stripped.lower()

    verify_markers = [
        "verify ",
        "check that ",
        "confirm that ",
        "確認",
        "檢查",
        "驗證",
    ]
    if any(marker in lowered for marker in verify_markers):
        return True

    if re_search_any(
        lowered,
        [
            r"\brun\s+[A-Za-z0-9_\-./\\]+\.py\b",
            r"\bexecute\s+[A-Za-z0-9_\-./\\]+\.py\b",
            r"\brun python file\b",
            r"\brun python script\b",
            r"\bexecute python file\b",
            r"\bexecute python script\b",
        ],
    ):
        return True

    if _extract_document_task_payload(stripped) is not None:
        return True

    return False


def re_search_any(text: str, patterns: List[str]) -> bool:
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def _extract_step_result_text(result: Any) -> str:
    if isinstance(result, str):
        return result.strip()

    if not isinstance(result, dict):
        return ""

    for key in ("text", "content", "message", "stdout", "stderr", "final_answer"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    result_block = result.get("result")
    if isinstance(result_block, dict):
        for key in ("text", "content", "message", "stdout", "stderr", "final_answer"):
            value = result_block.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return ""


def _print_direct_step_flow_result(plan_result: Dict[str, Any], execution_result: Dict[str, Any]) -> None:
    results = execution_result.get("results")
    if not isinstance(results, list) or not results:
        print_json(
            {
                "ok": bool(execution_result.get("ok", False)),
                "plan": plan_result,
                "execution": execution_result,
            }
        )
        return

    if len(results) == 1:
        step_result = results[0]
        step = step_result.get("step", {}) if isinstance(step_result, dict) else {}
        step_type = _safe_str(step.get("type")).lower()

        if step_type == "verify":
            print("true" if bool(step_result.get("ok", False)) else "false")
            if not bool(step_result.get("ok", False)):
                error_text = _safe_str(step_result.get("error"))
                if error_text:
                    print(error_text)
            return

        if step_type == "run_python":
            text = _extract_step_result_text(step_result)
            if text:
                print(text)
                return
            print_json(step_result)
            return

    if not bool(execution_result.get("ok", False)):
        failed_index = execution_result.get("failed_step")
        payload = {
            "ok": False,
            "failed_step": failed_index,
            "plan": plan_result,
            "execution": execution_result,
        }
        print_json(payload)
        return

    text = _extract_step_result_text(results[-1])
    if text:
        print(text)
        return

    print_json(
        {
            "ok": True,
            "plan": plan_result,
            "execution": execution_result,
        }
    )


def handle_direct_step_flow(system: Any, text: str) -> bool:
    planner = _get_planner(system)
    step_executor = _get_step_executor(system)

    if planner is None or step_executor is None:
        return False

    direct_context = _build_direct_flow_context(text)

    try:
        plan_result = planner.plan(context=direct_context, user_input=text)
    except Exception as e:
        print_json(
            {
                "ok": False,
                "error": f"planner direct flow failed: {e}",
                "traceback": traceback.format_exc(),
                "input": text,
                "context": direct_context,
            }
        )
        return True

    if not isinstance(plan_result, dict):
        print_json(
            {
                "ok": False,
                "error": "planner returned invalid result",
                "input": text,
                "context": direct_context,
                "planner_result": plan_result,
            }
        )
        return True

    steps = plan_result.get("steps")
    if not isinstance(steps, list) or not steps:
        print_json(
            {
                "ok": False,
                "error": "planner returned no steps",
                "input": text,
                "context": direct_context,
                "planner_result": plan_result,
            }
        )
        return True

    try:
        execution_result = step_executor.execute_steps(
            steps=steps,
            task=None,
            context=direct_context,
        )
    except Exception as e:
        print_json(
            {
                "ok": False,
                "error": f"step executor direct flow failed: {e}",
                "traceback": traceback.format_exc(),
                "input": text,
                "context": direct_context,
                "planner_result": plan_result,
            }
        )
        return True

    _print_direct_step_flow_result(plan_result, execution_result)
    return True


def handle_natural_language(system: Any, text: str) -> None:
    if _should_use_direct_step_flow(text):
        handled = handle_direct_step_flow(system, text)
        if handled:
            return

    agent = _get_agent_loop(system)
    if agent is None:
        print_json({"ok": False, "error": "agent_loop not available", "input": text})
        return
    run_fn = getattr(agent, "run", None)
    if not callable(run_fn):
        print_json({"ok": False, "error": "agent_loop.run not available", "input": text})
        return
    try:
        result = run_fn(text)
        output_text = _extract_agent_output(result)
        if output_text:
            print(output_text)
            return
        print_json(result)
    except Exception as e:
        print_json({"ok": False, "error": f"natural language handling failed: {e}", "traceback": traceback.format_exc(), "input": text})


def handle_command(system: Any, text: str, cli_state: Dict[str, Any]) -> None:
    normalized = _normalize_cli_command(text)
    if normalized:
        text = normalized

    if text == "/help":
        print_help()
        return
    if text == "/health":
        print_json(_build_health_info(system))
        return
    if text == "/runtime":
        print_json(_build_runtime_info(system))
        return
    if text == "/doc_summary":
        handle_natural_language(system, "summarize input.txt into summary.txt")
        return
    if text == "/doc_action_items":
        handle_natural_language(system, "read input.txt and extract action items into action_items.txt")
        return
    if text == "/task_list":
        _print_task_table(_list_tasks(system))
        return
    if text.startswith("/task_show "):
        task_id = text.split(maxsplit=1)[1].strip()
        task = _get_task(system, task_id)
        if not isinstance(task, dict):
            print_json({"ok": False, "error": "task not found", "task_id": task_id})
            return
        _print_task_summary(task)
        return
    if text.startswith("/task_result "):
        task_id = text.split(maxsplit=1)[1].strip()
        task = _get_task(system, task_id)
        if not isinstance(task, dict):
            print_json({"ok": False, "error": "task not found", "task_id": task_id})
            return
        _print_task_result(task)
        return
    if text.startswith("/task_open "):
        raw_args = text.split(maxsplit=1)[1].strip()
        task_id, selector = _parse_task_open_args(raw_args)
        if not task_id:
            print_json({"ok": False, "error": "task_id is required"})
            return
        task = _get_task(system, task_id)
        if not isinstance(task, dict):
            print_json({"ok": False, "error": "task not found", "task_id": task_id})
            return
        chosen, targets = _pick_open_target(task, selector=selector)
        if chosen is None:
            print_json({"ok": False, "error": "no open target available", "task_id": task_id, "selector": selector})
            return
        open_ok, open_error = _open_local_path(_safe_str(chosen.get("path")))
        response = {"ok": open_ok, "task_id": task_id, "selector": selector or "auto", "opened": _safe_str(chosen.get("path")), "target_name": _safe_str(chosen.get("name")), "target_kind": _safe_str(chosen.get("kind")), "exists": bool(chosen.get("exists")), "available_targets": targets}
        if open_error:
            response["error"] = open_error
        print_json(response)
        return
    if text.startswith("/task_delete "):
        task_id = text.split(maxsplit=1)[1].strip()
        if not task_id:
            print_json({"ok": False, "error": "task_id is required"})
            return
        print_json(_delete_task_from_repo(system, task_id))
        return
    if text.startswith("/task_retry "):
        task_id = text.split(maxsplit=1)[1].strip()
        if not task_id:
            print_json({"ok": False, "error": "task_id is required"})
            return
        print_json(_retry_task(system, task_id))
        return
    if text.startswith("/task_rerun "):
        task_id = text.split(maxsplit=1)[1].strip()
        if not task_id:
            print_json({"ok": False, "error": "task_id is required"})
            return
        result = _rerun_task(system, task_id)
        print_json(result)
        if result.get("new_task_id"):
            print("[hint]")
            print(f"新 task 已建立：{result['new_task_id']}")
            print("下一步可執行：")
            print("python app.py task list")
            print(f"python app.py task result {result['new_task_id']}")
        return
    if text.startswith("/task_purge "):
        mode = text.split(maxsplit=1)[1].strip().lower()
        if mode not in {"finished", "failed", "all"}:
            print_json({"ok": False, "error": "purge mode must be one of: finished / failed / all"})
            return
        print_json(_purge_tasks(system, mode))
        return
    if text.startswith("/task_doc_summary "):
        raw_args = text.split(maxsplit=1)[1].strip()
        input_file, output_file = _parse_doc_task_args(raw_args)
        if not input_file or not output_file:
            print_json({"ok": False, "error": "usage: task doc-summary <input> <output>"})
            return
        goal = _build_doc_task_goal("summary", input_file, output_file)
        result = _create_task(system, goal)
        if isinstance(result, dict):
            created_task = result.get("task", {}) if isinstance(result.get("task"), dict) else {}
            created_task_id = str(result.get("task_id") or result.get("task_name") or created_task.get("task_id") or created_task.get("task_name") or "").strip()
            if created_task_id:
                cli_state["last_created_task_id"] = created_task_id
        print_json(result)
        if cli_state.get("last_created_task_id"):
            print("[hint]")
            print(f"下一步可執行：submit {cli_state['last_created_task_id']}")
        return
    if text.startswith("/task_doc_action_items "):
        raw_args = text.split(maxsplit=1)[1].strip()
        input_file, output_file = _parse_doc_task_args(raw_args)
        if not input_file or not output_file:
            print_json({"ok": False, "error": "usage: task doc-action-items <input> <output>"})
            return
        goal = _build_doc_task_goal("action_items", input_file, output_file)
        result = _create_task(system, goal)
        if isinstance(result, dict):
            created_task = result.get("task", {}) if isinstance(result.get("task"), dict) else {}
            created_task_id = str(result.get("task_id") or result.get("task_name") or created_task.get("task_id") or created_task.get("task_name") or "").strip()
            if created_task_id:
                cli_state["last_created_task_id"] = created_task_id
        print_json(result)
        if cli_state.get("last_created_task_id"):
            print("[hint]")
            print(f"下一步可執行：submit {cli_state['last_created_task_id']}")
        return
    if text.startswith("/task_create "):
        goal = text.split(maxsplit=1)[1].strip()
        result = _create_task(system, goal)
        if isinstance(result, dict):
            created_task = result.get("task", {}) if isinstance(result.get("task"), dict) else {}
            created_task_id = str(result.get("task_id") or result.get("task_name") or created_task.get("task_id") or created_task.get("task_name") or "").strip()
            if created_task_id:
                cli_state["last_created_task_id"] = created_task_id
        print_json(result)
        if cli_state.get("last_created_task_id"):
            print("[hint]")
            print(f"下一步可執行：submit {cli_state['last_created_task_id']}")
        return
    if text == "/task_submit" or text.startswith("/task_submit "):
        task_id = ""
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            task_id = parts[1].strip()
        if not task_id:
            task_id = str(cli_state.get("last_created_task_id") or "").strip()
        if not task_id:
            print_json({"ok": False, "error": "task_id is required", "message": "先 create，或使用 submit <task_id>"})
            return
        result = _submit_existing_task(system, task_id)
        print_json(result)
        task = _get_task(system, task_id)
        if isinstance(task, dict):
            print("[task_status]")
            print(task.get("status"))
        return
    if text.startswith("/task_run"):
        parts = text.split()
        count = 1
        if len(parts) >= 2:
            try:
                count = max(1, int(parts[1]))
            except Exception:
                count = 1
        results = [{"tick_index": i + 1, "result": _run_once(system)} for i in range(count)]
        print_json({"ok": True, "count": count, "results": results})
        return
    if text.lower().startswith("chat "):
        message = text[5:].strip()
        if not message:
            print_json({"ok": False, "error": "chat message is empty"})
            return
        handle_natural_language(system, message)
        return
    if text.lower().startswith("ask "):
        message = text[4:].strip()
        if not message:
            print_json({"ok": False, "error": "ask message is empty"})
            return
        handle_natural_language(system, message)
        return
    print("未知指令，輸入 /help 查看說明。")


def _parse_cli_options(argv: List[str]) -> Tuple[List[str], Dict[str, Optional[str]]]:
    remaining: List[str] = []
    options: Dict[str, Optional[str]] = {"model": None, "plugin": None}
    i = 0
    while i < len(argv):
        token = str(argv[i]).strip()
        if token == "--model":
            if i + 1 >= len(argv):
                raise ValueError("--model 缺少值")
            options["model"] = str(argv[i + 1]).strip() or None
            i += 2
            continue
        if token.startswith("--model="):
            options["model"] = token.split("=", 1)[1].strip() or None
            i += 1
            continue
        if token == "--plugin":
            if i + 1 >= len(argv):
                raise ValueError("--plugin 缺少值")
            options["plugin"] = str(argv[i + 1]).strip() or None
            i += 2
            continue
        if token.startswith("--plugin="):
            options["plugin"] = token.split("=", 1)[1].strip() or None
            i += 1
            continue
        remaining.append(argv[i])
        i += 1
    return remaining, options


def _apply_cli_model_overrides(options: Dict[str, Optional[str]]) -> None:
    model = str(options.get("model") or "").strip()
    plugin = str(options.get("plugin") or "").strip()
    if model:
        os.environ["ZERO_MODEL"] = model
    if plugin:
        os.environ["ZERO_LLM_PLUGIN"] = plugin


def _argv_to_command(argv: List[str]) -> Optional[str]:
    if not argv:
        return None
    parts = [str(x).strip() for x in argv if str(x).strip()]
    if not parts:
        return None
    first = parts[0].lower()
    if first in {"help", "--help", "-h"}:
        return "/help"
    if first == "health":
        return "/health"
    if first == "runtime":
        return "/runtime"
    if first == "doc":
        if len(parts) == 1:
            return "/help"
        sub = parts[1].lower()
        if sub == "summary":
            return "/doc_summary"
        if sub in {"action_items", "action-items", "actionitems"}:
            return "/doc_action_items"
        return None
    if first == "task":
        if len(parts) == 1:
            return "/help"

        sub = parts[1].lower()

        if sub == "doc-summary" and len(parts) >= 4:
            return "/task_doc_summary " + " ".join(parts[2:4])

        if sub == "doc-action-items" and len(parts) >= 4:
            return "/task_doc_action_items " + " ".join(parts[2:4])

        if sub == "doc-action_items" and len(parts) >= 4:
            return "/task_doc_action_items " + " ".join(parts[2:4])

        if sub == "doc" and len(parts) >= 5:
            doc_mode = parts[2].lower()
            if doc_mode == "summary":
                return "/task_doc_summary " + " ".join(parts[3:5])
            if doc_mode in {"action-items", "action_items", "actionitems"}:
                return "/task_doc_action_items " + " ".join(parts[3:5])

        if sub == "list":
            return "/task_list"
        if sub == "show" and len(parts) >= 3:
            return "/task_show " + " ".join(parts[2:])
        if sub == "result" and len(parts) >= 3:
            return "/task_result " + " ".join(parts[2:])
        if sub == "open" and len(parts) >= 3:
            return "/task_open " + " ".join(parts[2:])
        if sub == "delete" and len(parts) >= 3:
            return "/task_delete " + " ".join(parts[2:])
        if sub == "retry" and len(parts) >= 3:
            return "/task_retry " + " ".join(parts[2:])
        if sub == "rerun" and len(parts) >= 3:
            return "/task_rerun " + " ".join(parts[2:])
        if sub == "purge" and len(parts) >= 3:
            return "/task_purge " + " ".join(parts[2:])
        if sub == "create" and len(parts) >= 3:
            return "/task_create " + " ".join(parts[2:])
        if sub == "submit":
            return "/task_submit " + " ".join(parts[2:]) if len(parts) >= 3 else "/task_submit"
        if sub == "run":
            return "/task_run " + " ".join(parts[2:]) if len(parts) >= 3 else "/task_run 1"
        return None
    if first == "chat":
        return "chat " + " ".join(parts[1:]) if len(parts) >= 2 else None
    if first == "ask":
        return "ask " + " ".join(parts[1:]) if len(parts) >= 2 else None
    mapping = {
        "list": "/task_list",
    }
    if first in mapping:
        return mapping[first]
    one_arg_map = {"show": "/task_show ", "result": "/task_result ", "open": "/task_open ", "delete": "/task_delete ", "retry": "/task_retry ", "rerun": "/task_rerun ", "purge": "/task_purge ", "create": "/task_create ", "submit": "/task_submit ", "run": "/task_run "}
    if first in one_arg_map:
        if len(parts) >= 2:
            return one_arg_map[first] + " ".join(parts[1:])
        return "/task_submit" if first == "submit" else "/task_run 1" if first == "run" else None
    return " ".join(parts)


def _boot_system_for_cli() -> Any:
    sink = io.StringIO()
    with redirect_stdout(sink):
        return boot_system(workspace_dir=WORKSPACE_DIR)


def _boot_system_for_interactive() -> Any:
    return boot_system(workspace_dir=WORKSPACE_DIR)


def run_cli_command_mode(argv: List[str]) -> int:
    cli_state: Dict[str, Any] = {"last_created_task_id": ""}
    try:
        remaining_argv, options = _parse_cli_options(argv)
    except ValueError as e:
        print_json({"ok": False, "error": str(e)})
        return 1
    command = _argv_to_command(remaining_argv)
    if not command:
        print("無法解析命令。輸入 python app.py help 查看說明。")
        return 1
    if command == "/help":
        print_help()
        return 0
    _apply_cli_model_overrides(options)
    system = _boot_system_for_cli()
    normalized = _normalize_cli_command(command)
    final_command = normalized or command
    if final_command.startswith("/") or normalized is not None:
        handle_command(system, final_command, cli_state)
        return 0
    handle_natural_language(system, final_command)
    return 0


def run_interactive_mode() -> int:
    cli_state: Dict[str, Any] = {"last_created_task_id": ""}
    system = _boot_system_for_interactive()
    print("ZERO Task OS")
    print("輸入 /help 查看指令。")
    while True:
        try:
            text = input("ZERO> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已離開。")
            return 0
        if not text:
            continue
        if text in ("/exit", "/quit", "exit", "quit"):
            print("已離開。")
            return 0
        normalized = _normalize_cli_command(text)
        if text.startswith("/") or normalized is not None:
            handle_command(system, text, cli_state)
            continue
        handle_natural_language(system, text)


def main() -> int:
    argv = sys.argv[1:]
    if argv:
        return run_cli_command_mode(argv)
    return run_interactive_mode()


if __name__ == "__main__":
    raise SystemExit(main())