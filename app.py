from __future__ import annotations

import copy
import io
import json
import os
import shutil
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
    print("  list")
    print("  show <task_id>")
    print("  result <task_id>")
    print("  open <task_id>")
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
    print("  task open <task_id>")
    print("  task delete <task_id>")
    print("  task retry <task_id>")
    print("  task rerun <task_id>")
    print("  task purge finished")
    print("  task purge failed")
    print("  task purge all")
    print("  task create <goal>")
    print("  task submit [task_id]")
    print("  task run [count]")
    print("  chat <message>")
    print("  ask <message>")
    print("  health")
    print("  runtime")
    print("  exit / quit")
    print("")
    print("命令列模式：")
    print("  python app.py task list")
    print("  python app.py task show <task_id>")
    print("  python app.py task result <task_id>")
    print("  python app.py task open <task_id>")
    print("  python app.py task delete <task_id>")
    print("  python app.py task retry <task_id>")
    print("  python app.py task rerun <task_id>")
    print("  python app.py task purge finished")
    print('  python app.py chat "你好"')
    print('  python app.py ask "幫我建立一個檔案"')
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
    value = _find_first_value(
        task,
        [
            "final_answer",
            "answer",
            "response",
            "message",
            "summary",
            "result_text",
            "content",
        ],
    )
    if isinstance(value, str):
        return value.strip()
    return ""


def _extract_goal(task: Dict[str, Any]) -> str:
    return _first_nonempty_str(
        task.get("goal"),
        task.get("title"),
        task.get("prompt"),
        task.get("query"),
        task.get("input"),
    )


def _extract_task_id(task: Dict[str, Any]) -> str:
    return _first_nonempty_str(
        task.get("task_id"),
        task.get("task_name"),
        task.get("id"),
        task.get("name"),
    )


def _extract_status(task: Dict[str, Any]) -> str:
    return _first_nonempty_str(task.get("status"), "unknown")


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
    value = _find_first_value(
        task,
        [
            "current_step",
            "current_step_title",
            "current_step_name",
            "step_title",
            "step_name",
        ],
    )
    if isinstance(value, str):
        return value.strip()

    steps = task.get("steps")
    idx = _extract_current_step_index(task)
    if isinstance(steps, list) and 0 <= idx < len(steps):
        step = steps[idx]
        if isinstance(step, dict):
            return _first_nonempty_str(
                step.get("title"),
                step.get("name"),
                step.get("description"),
                step.get("goal"),
            )
        if isinstance(step, str):
            return step.strip()

    return ""


def _extract_paths(task: Dict[str, Any]) -> Dict[str, str]:
    candidates = {
        "task_dir": [
            "task_dir",
            "task_path",
            "workspace_path",
            "work_dir",
            "working_dir",
            "sandbox_dir",
        ],
        "result_path": [
            "result_path",
            "output_path",
            "artifact_path",
            "final_output_path",
        ],
        "sandbox_path": [
            "sandbox_path",
            "sandbox_result_path",
            "sandbox_output_path",
        ],
        "plan_path": [
            "plan_path",
            "plan_file",
        ],
        "runtime_state_path": [
            "runtime_state_path",
            "runtime_state_file",
            "state_path",
        ],
        "execution_log_path": [
            "execution_log_path",
            "execution_log_file",
            "log_path",
        ],
    }

    result: Dict[str, str] = {}
    for output_key, keys in candidates.items():
        value = _find_first_value(task, keys)
        if isinstance(value, str) and value.strip():
            result[output_key] = value.strip()

    task_id = _extract_task_id(task)
    if task_id and "task_dir" not in result:
        result["task_dir"] = os.path.join(WORKSPACE_DIR, "tasks", task_id)

    if "plan_path" not in result and result.get("task_dir"):
        result["plan_path"] = os.path.join(result["task_dir"], "plan.json")

    if "runtime_state_path" not in result and result.get("task_dir"):
        result["runtime_state_path"] = os.path.join(result["task_dir"], "runtime_state.json")

    if "execution_log_path" not in result and result.get("task_dir"):
        result["execution_log_path"] = os.path.join(result["task_dir"], "execution_log.json")

    return result


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

        rows.append(
            {
                "task_id": _extract_task_id(task),
                "status": _extract_status(task),
                "step": _format_step_progress(task),
                "goal": _truncate_text(_extract_goal(task), 26),
                "result_summary": _truncate_text(_extract_final_answer(task), 42),
            }
        )

    if not rows:
        print("目前沒有 task。")
        return

    task_id_w = max(len("task_id"), min(24, max(len(r["task_id"]) for r in rows)))
    status_w = max(len("status"), min(12, max(len(r["status"]) for r in rows)))
    step_w = max(len("step"), min(8, max(len(r["step"]) for r in rows)))
    goal_w = max(len("goal"), min(26, max(len(r["goal"]) for r in rows)))

    header = (
        f"{'task_id':<{task_id_w}}  "
        f"{'status':<{status_w}}  "
        f"{'step':<{step_w}}  "
        f"{'goal':<{goal_w}}  "
        f"result_summary"
    )
    print(header)
    print("-" * max(100, len(header)))

    for row in rows:
        print(
            f"{row['task_id']:<{task_id_w}}  "
            f"{row['status']:<{status_w}}  "
            f"{row['step']:<{step_w}}  "
            f"{row['goal']:<{goal_w}}  "
            f"{row['result_summary']}"
        )


def _print_task_summary(task: Dict[str, Any]) -> None:
    task_id = _extract_task_id(task)
    status = _extract_status(task)
    goal = _extract_goal(task)
    step_progress = _format_step_progress(task)
    current_step_text = _extract_current_step_text(task)
    final_answer = _extract_final_answer(task)
    paths = _extract_paths(task)

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

    if paths:
        print("paths:")
        for key, value in paths.items():
            print(f"  {key}: {value}")


def _print_task_result(task: Dict[str, Any]) -> None:
    task_id = _extract_task_id(task)
    status = _extract_status(task)
    final_answer = _extract_final_answer(task)
    paths = _extract_paths(task)

    print(f"task_id: {task_id}")
    print(f"status: {status}")

    if final_answer:
        print("final_answer:")
        print(textwrap.indent(final_answer, "  "))
    else:
        print("final_answer:")
        print("  <empty>")

    visible_path_keys = [
        "result_path",
        "sandbox_path",
        "task_dir",
        "plan_path",
        "runtime_state_path",
        "execution_log_path",
    ]
    any_path = False
    for key in visible_path_keys:
        value = paths.get(key, "").strip()
        if value:
            if not any_path:
                print("paths:")
                any_path = True
            print(f"  {key}: {value}")


def _print_task_open(task: Dict[str, Any]) -> None:
    task_id = _extract_task_id(task)
    status = _extract_status(task)
    paths = _extract_paths(task)
    final_answer = _extract_final_answer(task)

    print(f"task_id: {task_id}")
    print(f"status: {status}")

    preferred_keys = [
        "task_dir",
        "result_path",
        "sandbox_path",
        "plan_path",
        "runtime_state_path",
        "execution_log_path",
    ]

    print("open_targets:")
    for key in preferred_keys:
        value = paths.get(key, "").strip()
        if value:
            print(f"  {key}: {value}")

    if final_answer:
        print("result_summary:")
        print(textwrap.indent(_truncate_text(final_answer, 240), "  "))


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
            return {
                "ok": False,
                "error": f"submit_existing_task failed: {e}",
                "task_id": task_id,
            }

    return {"ok": False, "error": "submit_existing_task not available", "task_id": task_id}


def _spawn_task_from_existing(system: Any, task_id: str, action_name: str) -> Dict[str, Any]:
    old_task = _get_task(system, task_id)
    if not isinstance(old_task, dict):
        return {
            "ok": False,
            "error": "source task not found",
            "source_task_id": task_id,
            "action": action_name,
        }

    goal = _extract_goal(old_task)
    if not goal:
        return {
            "ok": False,
            "error": "source task goal is empty",
            "source_task_id": task_id,
            "action": action_name,
        }

    create_result = _create_task(system, goal)
    if not isinstance(create_result, dict) or not create_result.get("ok", False):
        return {
            "ok": False,
            "error": "create_task failed",
            "source_task_id": task_id,
            "goal": goal,
            "action": action_name,
            "create_result": create_result,
        }

    new_task_id = _first_nonempty_str(
        create_result.get("task_id"),
        create_result.get("task_name"),
        (create_result.get("task", {}) if isinstance(create_result.get("task"), dict) else {}).get("task_id"),
        (create_result.get("task", {}) if isinstance(create_result.get("task"), dict) else {}).get("task_name"),
    )

    if not new_task_id:
        return {
            "ok": False,
            "error": "created task but no task_id returned",
            "source_task_id": task_id,
            "goal": goal,
            "action": action_name,
            "create_result": create_result,
        }

    submit_result = _submit_existing_task(system, new_task_id)

    return {
        "ok": bool(submit_result.get("ok", False)) if isinstance(submit_result, dict) else False,
        "action": action_name,
        "source_task_id": task_id,
        "new_task_id": new_task_id,
        "goal": goal,
        "create_result": create_result,
        "submit_result": submit_result,
    }


def _retry_task(system: Any, task_id: str) -> Dict[str, Any]:
    return _spawn_task_from_existing(system, task_id, action_name="task_retry")


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

    return {
        "ok": removed,
        "task_id": task_id,
        "errors": errors,
    }


def _purge_tasks(system: Any, mode: str) -> Dict[str, Any]:
    tasks = _list_tasks(system)
    deleted: List[str] = []
    failed: List[Dict[str, Any]] = []

    for task in tasks:
        if not isinstance(task, dict):
            continue

        task_id = _extract_task_id(task)
        status = _extract_status(task).lower()

        should_delete = False
        if mode == "all":
            should_delete = True
        elif mode == "finished" and status in {"finished", "completed", "done", "success"}:
            should_delete = True
        elif mode == "failed" and status in {"failed", "error"}:
            should_delete = True

        if not should_delete or not task_id:
            continue

        result = _delete_task_from_repo(system, task_id)
        if result.get("ok"):
            deleted.append(task_id)
        else:
            failed.append(
                {
                    "task_id": task_id,
                    "errors": result.get("errors", []),
                }
            )

    return {
        "ok": True,
        "mode": mode,
        "deleted_count": len(deleted),
        "deleted": deleted,
        "failed_count": len(failed),
        "failed": failed,
    }


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
    if lowered == "runtime":
        return "/runtime"
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
    if lowered == "submit":
        return "/task_submit"
    if lowered.startswith("submit "):
        return "/task_submit " + stripped[7:].strip()
    if lowered.startswith("show "):
        return "/task_show " + stripped[5:].strip()
    if lowered.startswith("result "):
        return "/task_result " + stripped[7:].strip()
    if lowered.startswith("open "):
        return "/task_open " + stripped[5:].strip()
    if lowered.startswith("delete "):
        return "/task_delete " + stripped[7:].strip()
    if lowered.startswith("retry "):
        return "/task_retry " + stripped[6:].strip()
    if lowered.startswith("rerun "):
        return "/task_rerun " + stripped[6:].strip()
    if lowered.startswith("purge "):
        return "/task_purge " + stripped[6:].strip()
    if lowered.startswith("chat "):
        return stripped
    if lowered.startswith("ask "):
        return stripped

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
    if lowered == "task submit":
        return "/task_submit"
    if lowered.startswith("task submit "):
        return "/task_submit " + stripped[12:].strip()
    if lowered.startswith("task show "):
        return "/task_show " + stripped[10:].strip()
    if lowered.startswith("task result "):
        return "/task_result " + stripped[12:].strip()
    if lowered.startswith("task open "):
        return "/task_open " + stripped[10:].strip()
    if lowered.startswith("task delete "):
        return "/task_delete " + stripped[12:].strip()
    if lowered.startswith("task retry "):
        return "/task_retry " + stripped[11:].strip()
    if lowered.startswith("task rerun "):
        return "/task_rerun " + stripped[11:].strip()
    if lowered.startswith("task purge "):
        return "/task_purge " + stripped[11:].strip()

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

    llm_client = getattr(agent, "llm_client", None)
    if llm_client is None:
        llm_client = getattr(system, "llm_client", None)
    if llm_client is None and scheduler is not None:
        llm_client = getattr(scheduler, "llm_client", None)

    runtime_info: Dict[str, Any] = {
        "ok": True,
        "app": "ZERO Task OS",
        "workspace_dir": WORKSPACE_DIR,
        "has_scheduler": scheduler is not None,
        "has_agent_loop": agent is not None,
        "llm": {
            "plugin_name": "",
            "provider": "",
            "base_url": "",
            "model": "",
            "coder_model": "",
            "timeout": None,
        },
    }

    get_runtime_info_fn = getattr(llm_client, "get_runtime_info", None)
    if callable(get_runtime_info_fn):
        try:
            runtime_info["llm"] = get_runtime_info_fn()
            return runtime_info
        except Exception as e:
            runtime_info["llm_error"] = f"get_runtime_info failed: {e}"
            return runtime_info

    runtime_info["llm"] = {
        "plugin_name": _safe_str(getattr(llm_client, "plugin_name", "")),
        "provider": _safe_str(getattr(llm_client, "provider", "")),
        "base_url": _safe_str(getattr(llm_client, "base_url", "")),
        "model": _safe_str(getattr(llm_client, "model", "")),
        "coder_model": _safe_str(getattr(llm_client, "coder_model", "")),
        "timeout": getattr(llm_client, "timeout", None),
    }
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
            base_health = {
                "ok": False,
                "error": f"health() failed: {e}",
            }

    runtime = _build_runtime_info(system)
    merged = {
        "ok": True,
        "workspace_dir": WORKSPACE_DIR,
        "runtime": runtime,
    }
    merged.update(base_health)
    return merged


def handle_natural_language(system: Any, text: str) -> None:
    agent = _get_agent_loop(system)
    if agent is None:
        print_json({
            "ok": False,
            "error": "agent_loop not available",
            "input": text,
        })
        return

    run_fn = getattr(agent, "run", None)
    if not callable(run_fn):
        print_json({
            "ok": False,
            "error": "agent_loop.run not available",
            "input": text,
        })
        return

    try:
        result = run_fn(text)

        output_text = _extract_agent_output(result)
        if output_text:
            print(output_text)
            return

        print_json(result)

    except Exception as e:
        print_json({
            "ok": False,
            "error": f"natural language handling failed: {e}",
            "traceback": traceback.format_exc(),
            "input": text,
        })


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
        task_id = text.split(maxsplit=1)[1].strip()
        task = _get_task(system, task_id)
        if not isinstance(task, dict):
            print_json({"ok": False, "error": "task not found", "task_id": task_id})
            return
        _print_task_open(task)
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
        result = _retry_task(system, task_id)
        print_json(result)
        if result.get("new_task_id"):
            print("[hint]")
            print(f"新 task 已建立：{result['new_task_id']}")
            print("下一步可執行：")
            print("python app.py task list")
            print(f"python app.py task result {result['new_task_id']}")
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
            print_json(
                {
                    "ok": False,
                    "error": "purge mode must be one of: finished / failed / all",
                }
            )
            return
        print_json(_purge_tasks(system, mode))
        return

    if text.startswith("/task_create "):
        goal = text.split(maxsplit=1)[1].strip()
        result = _create_task(system, goal)

        if isinstance(result, dict):
            created_task_id = str(
                result.get("task_id")
                or result.get("task_name")
                or (result.get("task", {}) if isinstance(result.get("task"), dict) else {}).get("task_id")
                or (result.get("task", {}) if isinstance(result.get("task"), dict) else {}).get("task_name")
                or ""
            ).strip()

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
            print_json({
                "ok": False,
                "error": "task_id is required",
                "message": "先 create，或使用 submit <task_id>",
            })
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

        results = []
        for i in range(count):
            results.append({"tick_index": i + 1, "result": _run_once(system)})

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
    options: Dict[str, Optional[str]] = {
        "model": None,
        "plugin": None,
    }

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

    if first == "task":
        if len(parts) == 1:
            return "/help"

        sub = parts[1].lower()

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
            if len(parts) >= 3:
                return "/task_submit " + " ".join(parts[2:])
            return "/task_submit"

        if sub == "run":
            if len(parts) >= 3:
                return "/task_run " + " ".join(parts[2:])
            return "/task_run 1"

        return None

    if first == "chat":
        if len(parts) >= 2:
            return "chat " + " ".join(parts[1:])
        return None

    if first == "ask":
        if len(parts) >= 2:
            return "ask " + " ".join(parts[1:])
        return None

    if first == "list":
        return "/task_list"

    if first == "show" and len(parts) >= 2:
        return "/task_show " + " ".join(parts[1:])

    if first == "result" and len(parts) >= 2:
        return "/task_result " + " ".join(parts[1:])

    if first == "open" and len(parts) >= 2:
        return "/task_open " + " ".join(parts[1:])

    if first == "delete" and len(parts) >= 2:
        return "/task_delete " + " ".join(parts[1:])

    if first == "retry" and len(parts) >= 2:
        return "/task_retry " + " ".join(parts[1:])

    if first == "rerun" and len(parts) >= 2:
        return "/task_rerun " + " ".join(parts[1:])

    if first == "purge" and len(parts) >= 2:
        return "/task_purge " + " ".join(parts[1:])

    if first == "create" and len(parts) >= 2:
        return "/task_create " + " ".join(parts[1:])

    if first == "submit":
        if len(parts) >= 2:
            return "/task_submit " + " ".join(parts[1:])
        return "/task_submit"

    if first == "run":
        if len(parts) >= 2:
            return "/task_run " + " ".join(parts[1:])
        return "/task_run 1"

    return " ".join(parts)


def _boot_system_for_cli() -> Any:
    sink = io.StringIO()
    with redirect_stdout(sink):
        return boot_system(workspace_dir=WORKSPACE_DIR)


def _boot_system_for_interactive() -> Any:
    return boot_system(workspace_dir=WORKSPACE_DIR)


def run_cli_command_mode(argv: List[str]) -> int:
    cli_state: Dict[str, Any] = {
        "last_created_task_id": "",
    }

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
    cli_state: Dict[str, Any] = {
        "last_created_task_id": "",
    }

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