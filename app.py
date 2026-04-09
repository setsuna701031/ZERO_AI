from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Optional

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
    print("  list")
    print("  show <task_id>")
    print("  create <goal>")
    print("  submit <task_id>")
    print("  run [count]")
    print("  tick")
    print("  task list")
    print("  task show <task_id>")
    print("  task create <goal>")
    print("  task submit <task_id>")
    print("  task run [count]")
    print("  exit / quit")


def _get_scheduler(system: Any) -> Any:
    scheduler = getattr(system, "scheduler", None)
    if scheduler is not None:
        return scheduler
    return system


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


def _print_task_table(tasks: List[Dict[str, Any]]) -> None:
    print("task_name | status | step | goal")
    print("-" * 100)
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_name = str(task.get("task_name") or task.get("task_id") or "").strip()
        status = str(task.get("status") or "").strip()
        current_step_index = task.get("current_step_index")
        steps_total = task.get("steps_total")
        goal = str(task.get("goal") or task.get("title") or "").strip()
        step_text = f"{current_step_index}/{steps_total}"
        print(f"{task_name} | {status} | {step_text} | {goal}")


def _create_task(system: Any, goal: str) -> Dict[str, Any]:
    scheduler = _get_scheduler(system)
    create_fn = getattr(scheduler, "create_task", None)
    if callable(create_fn):
        try:
            result = create_fn(
                goal=goal,
                priority=0,
                max_retries=0,
                retry_delay=0,
                timeout_ticks=0,
            )
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


def _normalize_cli_command(text: str) -> Optional[str]:
    stripped = str(text or "").strip()
    if not stripped:
        return None

    if stripped.startswith("/"):
        return stripped

    lowered = stripped.lower()

    if lowered == "help":
        return "/help"
    if lowered == "health":
        return "/health"
    if lowered == "list":
        return "/task_list"
    if lowered == "tick":
        return "/task_run 1"
    if lowered == "run":
        return "/task_run 1"
    if lowered.startswith("run "):
        return "/task_run " + stripped[4:].strip()
    if lowered.startswith("create "):
        return "/task_create " + stripped[7:].strip()
    if lowered.startswith("new "):
        return "/task_create " + stripped[4:].strip()
    if lowered.startswith("submit "):
        return "/task_submit " + stripped[7:].strip()
    if lowered.startswith("show "):
        return "/task_show " + stripped[5:].strip()

    # 支援 task 前綴
    if lowered == "task list":
        return "/task_list"
    if lowered == "task run":
        return "/task_run 1"
    if lowered.startswith("task run "):
        return "/task_run " + stripped[9:].strip()
    if lowered.startswith("task create "):
        return "/task_create " + stripped[12:].strip()
    if lowered.startswith("task new "):
        return "/task_create " + stripped[9:].strip()
    if lowered.startswith("task submit "):
        return "/task_submit " + stripped[12:].strip()
    if lowered.startswith("task show "):
        return "/task_show " + stripped[10:].strip()

    return None


def handle_command(system: Any, text: str) -> None:
    normalized = _normalize_cli_command(text)
    if normalized:
        text = normalized

    if text == "/help":
        print_help()
        return

    if text == "/health":
        health_fn = getattr(system, "health", None)
        if callable(health_fn):
            print_json(health_fn())
            return
        print_json({"ok": False, "error": "health not available"})
        return

    if text == "/task_list":
        _print_task_table(_list_tasks(system))
        return

    if text.startswith("/task_show "):
        task_id = text.split(maxsplit=1)[1].strip()
        print_json(_get_task(system, task_id) or {"ok": False, "error": "task not found", "task_id": task_id})
        return

    if text.startswith("/task_create "):
        goal = text.split(maxsplit=1)[1].strip()
        print_json(_create_task(system, goal))
        return

    if text.startswith("/task_submit "):
        task_id = text.split(maxsplit=1)[1].strip()
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
        results = []
        for i in range(count):
            results.append({"tick_index": i + 1, "result": _run_once(system)})
        print_json({"ok": True, "count": count, "results": results})
        return

    print("未知指令，輸入 /help 查看說明。")


def main() -> None:
    system = boot_system(workspace_dir=WORKSPACE_DIR)

    print("ZERO Task OS")
    print("輸入 /help 查看指令。")

    while True:
        try:
            text = input("ZERO> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已離開。")
            break

        if not text:
            continue

        if text in ("/exit", "/quit", "exit", "quit"):
            print("已離開。")
            break

        normalized = _normalize_cli_command(text)
        if text.startswith("/") or normalized is not None:
            handle_command(system, text)
            continue

        print("請使用明確指令：create / submit / run / list")


if __name__ == "__main__":
    main()