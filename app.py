from __future__ import annotations

import copy
import json
import os
import time
from typing import Any, Dict, Optional

from services.system_boot import boot_system


WORKSPACE_DIR = os.environ.get("ZERO_WORKSPACE", "workspace")

TERMINAL_STATUSES = {
    "finished",
    "completed",
    "failed",
    "canceled",
}


def print_help() -> None:
    print("可用指令：")
    print("  /help                                   顯示說明")
    print("  /health                                 系統健康狀態")
    print("  /tools                                  顯示目前已註冊工具")
    print("  /executor                               顯示 step_executor 物件資訊")
    print("  /queue                                  顯示任務佇列")
    print("  /tasks                                  顯示任務快照")
    print("  /task <task_name>                       顯示單一任務")
    print("  /tick                                   執行一次 scheduler tick")
    print("  /run <count>                            連續執行多次 tick")
    print("  /pause <task_name>                      暫停任務")
    print("  /resume <task_name>                     恢復任務")
    print("  /cancel <task_name>                     取消任務")
    print("  /priority <task> <num>                  設定任務優先級")
    print("")
    print("Task OS 別名指令：")
    print("  /task_submit <goal>                     建立任務並持續執行到完成或達到上限")
    print("  /task_create <goal>                     只建立任務，不立刻執行")
    print("  /task_submit_retry <max> <delay> <goal> 建立可重試任務並持續執行")
    print("  /task_create_retry <max> <delay> <goal> 建立可重試任務，不立刻執行")
    print("  /retrytask <max> <delay> <goal>         /task_submit_retry 的簡寫")
    print("  /task_list                              顯示任務佇列")
    print("  /task_tasks                             顯示任務快照")
    print("  /task_show <task_name>                  顯示單一任務")
    print("  /task_tick                              執行一次 scheduler tick")
    print("  /task_run <count>                       連續執行多次 tick")
    print("  /task_pause <task_name>                 暫停任務")
    print("  /task_resume <task_name>                恢復任務")
    print("  /task_cancel <task_name>                取消任務")
    print("  /task_priority <task> <num>             設定任務優先級")
    print("")
    print("  其他自然語言輸入會直接建立任務並持續執行")
    print("  /exit                                   離開")
    print("  /quit                                   離開")


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def summarize_tool_result(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result)

    if "final_answer" in result and result.get("final_answer"):
        return str(result["final_answer"])

    if result.get("success") is True:
        if "stdout" in result and result.get("stdout"):
            return str(result["stdout"])
        if "message" in result and result.get("message"):
            return str(result["message"])

    if "message" in result and result.get("message"):
        return str(result["message"])

    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


def print_execution_log(execution_log: Any) -> None:
    if not isinstance(execution_log, list) or not execution_log:
        return

    print("[execution_log]")
    print_json(execution_log)

    last_item = execution_log[-1]
    if not isinstance(last_item, dict):
        return

    result = last_item.get("result")
    if result is None:
        result = last_item.get("data")

    if result is None:
        return

    summary = summarize_tool_result(result)
    if summary:
        print("[result]")
        print(summary)


def _extract_task_name(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("task_name", "task_id", "id", "name"):
            v = value.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    elif isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return ""


def _extract_submit_task_name(submit_result: Dict[str, Any]) -> str:
    if not isinstance(submit_result, dict):
        return ""

    direct = _extract_task_name(submit_result)
    if direct:
        return direct

    task_obj = submit_result.get("task")
    nested = _extract_task_name(task_obj)
    if nested:
        return nested

    enqueue_result = submit_result.get("enqueue_result")
    nested2 = _extract_task_name(enqueue_result)
    if nested2:
        return nested2

    return ""


def _get_system_task(system: Any, task_name: str) -> Dict[str, Any]:
    if not task_name:
        return {"ok": False, "error": "empty task_name"}

    get_task_fn = getattr(system, "get_task", None)
    if callable(get_task_fn):
        try:
            result = get_task_fn(task_name)
            if isinstance(result, dict):
                return result
        except Exception as e:
            return {"ok": False, "error": f"system.get_task failed: {e}"}

    task_manager = getattr(system, "task_manager", None)
    if task_manager is not None:
        load_task_fn = getattr(task_manager, "load_task", None)
        if callable(load_task_fn):
            try:
                task_obj = load_task_fn(task_name)
                if task_obj is None:
                    return {"ok": False, "error": "task not found"}

                to_dict = getattr(task_obj, "to_dict", None)
                if callable(to_dict):
                    return {"ok": True, "task": to_dict()}

                if isinstance(task_obj, dict):
                    return {"ok": True, "task": copy.deepcopy(task_obj)}

                if hasattr(task_obj, "__dict__"):
                    return {"ok": True, "task": copy.deepcopy(vars(task_obj))}
            except Exception as e:
                return {"ok": False, "error": f"task_manager.load_task failed: {e}"}

    return {"ok": False, "error": "no available get_task path"}


def _extract_task_from_result(result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {}

    task = result.get("task")
    if isinstance(task, dict):
        return task

    return {}


def _get_task_status(system: Any, task_name: str) -> str:
    task_result = _get_system_task(system, task_name)
    if not task_result.get("ok"):
        return ""

    task = task_result.get("task", {})
    status = task.get("status")
    if isinstance(status, str):
        return status.strip()

    return ""


def _run_scheduler_once(system: Any) -> Dict[str, Any]:
    """
    盡量用最直接的方式推動 scheduler/runner 執行一次。
    優先順序：
    1. system.tick()
    2. scheduler.run_once()
    """
    tick_fn = getattr(system, "tick", None)
    if callable(tick_fn):
        try:
            result = tick_fn()
            if isinstance(result, dict):
                return result
            return {"ok": True, "result": result}
        except Exception as e:
            return {"ok": False, "error": f"system.tick failed: {e}"}

    scheduler = getattr(system, "scheduler", None)
    if scheduler is not None:
        run_once_fn = getattr(scheduler, "run_once", None)
        if callable(run_once_fn):
            try:
                result = run_once_fn()
                if isinstance(result, dict):
                    return result
                return {"ok": True, "ran": bool(result)}
            except Exception as e:
                return {"ok": False, "error": f"scheduler.run_once failed: {e}"}

    return {"ok": False, "error": "no available tick method"}


def _run_scheduler_until_task_done(
    system: Any,
    task_name: str,
    *,
    max_ticks: int = 20,
    sleep_sec: float = 0.0,
) -> Dict[str, Any]:
    """
    建任務後持續推進，直到指定 task 進入 terminal 狀態或達到 tick 上限。
    """
    history: list[Dict[str, Any]] = []

    for i in range(max_ticks):
        status_before = _get_task_status(system, task_name)

        if status_before in TERMINAL_STATUSES:
            return {
                "ok": True,
                "task_name": task_name,
                "tick_count": i,
                "status": status_before,
                "history": history,
                "message": "task already terminal before tick",
            }

        tick_result = _run_scheduler_once(system)
        history.append(
            {
                "tick_index": i + 1,
                "status_before": status_before,
                "tick_result": copy.deepcopy(tick_result),
                "status_after": _get_task_status(system, task_name),
            }
        )

        status_after = _get_task_status(system, task_name)
        if status_after in TERMINAL_STATUSES:
            return {
                "ok": True,
                "task_name": task_name,
                "tick_count": i + 1,
                "status": status_after,
                "history": history,
                "tick_result": tick_result,
                "message": "task reached terminal status",
            }

        if sleep_sec > 0:
            time.sleep(sleep_sec)

    return {
        "ok": False,
        "task_name": task_name,
        "tick_count": max_ticks,
        "status": _get_task_status(system, task_name),
        "history": history,
        "error": f"task did not reach terminal status within {max_ticks} ticks",
    }


def print_task_result(submit_result: Dict[str, Any], run_result: Dict[str, Any], system: Any) -> None:
    task_name = _extract_submit_task_name(submit_result)
    print(f"[task] {task_name or '(unknown)'}")

    if isinstance(run_result, dict) and not run_result.get("ok", True):
        print("[run_result]")
        print_json(run_result)

    task_result = _get_system_task(system, task_name)
    if not task_result.get("ok"):
        print("[task_lookup_failed]")
        print_json(task_result)
        return

    task = task_result.get("task", {})

    final_answer = task.get("final_answer")
    if isinstance(final_answer, str) and final_answer.strip():
        print(final_answer)

    execution_log = task.get("execution_log", [])
    if isinstance(execution_log, list) and execution_log:
        print_execution_log(execution_log)
    else:
        message = run_result.get("message") if isinstance(run_result, dict) else ""
        if message:
            print(message)

    print("[task_status]")
    print(task.get("status"))

    runtime_state_file = task.get("runtime_state_file")
    if runtime_state_file:
        print("[runtime_state_file]")
        print(runtime_state_file)


def submit_and_run(
    system: Any,
    goal: str,
    *,
    priority: int = 0,
    max_retries: int = 0,
    retry_delay: int = 0,
    timeout_ticks: int = 0,
) -> None:
    submit_result = system.submit_task(
        goal=goal,
        priority=priority,
        max_retries=max_retries,
        retry_delay=retry_delay,
        timeout_ticks=timeout_ticks,
    )

    if not isinstance(submit_result, dict) or not submit_result.get("ok"):
        print_json(submit_result)
        return

    task_name = _extract_submit_task_name(submit_result)
    if not task_name:
        print("[submit_result]")
        print_json(submit_result)
        print("找不到 task_name，無法追蹤執行。")
        return

    run_result = _run_scheduler_until_task_done(
        system,
        task_name,
        max_ticks=20 + (max_retries * (retry_delay + 2)),
        sleep_sec=0.0,
    )

    print_task_result(submit_result, run_result, system)


def create_task_only(
    system: Any,
    goal: str,
    *,
    priority: int = 0,
    max_retries: int = 0,
    retry_delay: int = 0,
    timeout_ticks: int = 0,
) -> None:
    submit_result = system.submit_task(
        goal=goal,
        priority=priority,
        max_retries=max_retries,
        retry_delay=retry_delay,
        timeout_ticks=timeout_ticks,
    )
    print_json(submit_result)


def _parse_retry_command(text: str) -> Optional[Dict[str, Any]]:
    parts = text.split(maxsplit=3)
    if len(parts) < 4:
        return None

    cmd = parts[0].strip()
    try:
        max_retries = int(parts[1])
        retry_delay = int(parts[2])
    except Exception:
        return None

    goal = parts[3].strip()
    if not goal:
        return None

    return {
        "cmd": cmd,
        "max_retries": max_retries,
        "retry_delay": retry_delay,
        "goal": goal,
    }


def handle_command(system: Any, text: str) -> None:
    if text == "/help":
        print_help()
        return

    if text == "/health":
        print_json(system.health())
        return

    if text == "/executor":
        step_executor = getattr(system.scheduler, "step_executor", None)
        if step_executor is None:
            print_json({
                "ok": False,
                "error": "step_executor 不存在",
            })
            return

        cls = step_executor.__class__
        attrs = sorted(
            name for name in dir(step_executor)
            if not name.startswith("__")
        )

        print_json({
            "ok": True,
            "type": str(type(step_executor)),
            "module": getattr(cls, "__module__", None),
            "class_name": getattr(cls, "__name__", None),
            "has_tool_registry_attr": hasattr(step_executor, "tool_registry"),
            "attrs": attrs,
        })
        return

    if text == "/tools":
        step_executor = getattr(system.scheduler, "step_executor", None)
        if step_executor is None:
            print_json({
                "ok": False,
                "error": "step_executor 不存在",
            })
            return

        if not hasattr(step_executor, "tool_registry"):
            cls = step_executor.__class__
            print_json({
                "ok": False,
                "error": "tool_registry 不存在",
                "executor_type": str(type(step_executor)),
                "module": getattr(cls, "__module__", None),
                "class_name": getattr(cls, "__name__", None),
            })
            return

        tool_registry = getattr(step_executor, "tool_registry", None)
        if tool_registry is None:
            print_json({
                "ok": False,
                "error": "tool_registry 是 None",
            })
            return

        list_tools_fn = getattr(tool_registry, "list_tools", None)
        if callable(list_tools_fn):
            try:
                print_json(list_tools_fn())
                return
            except Exception as e:
                print_json({
                    "ok": False,
                    "error": f"list_tools 執行失敗: {e}",
                })
                return

        tools_attr = getattr(tool_registry, "tools", None)
        if isinstance(tools_attr, dict):
            print_json({
                "ok": True,
                "count": len(tools_attr),
                "tools": sorted(tools_attr.keys()),
            })
            return

        private_tools_attr = getattr(tool_registry, "_tools", None)
        if isinstance(private_tools_attr, dict):
            print_json({
                "ok": True,
                "count": len(private_tools_attr),
                "tools": sorted(private_tools_attr.keys()),
            })
            return

        print_json({
            "ok": False,
            "error": "找不到可列出工具的方法",
            "tool_registry_type": str(type(tool_registry)),
        })
        return

    if text in ("/queue", "/task_list"):
        print_json(system.get_queue_rows())
        return

    if text in ("/tasks", "/task_tasks"):
        print_json(system.get_queue_snapshot())
        return

    if text in ("/tick", "/task_tick"):
        print_json(_run_scheduler_once(system))
        return

    if text.startswith("/run") or text.startswith("/task_run"):
        parts = text.split()
        count = 1
        if len(parts) >= 2:
            try:
                count = int(parts[1])
            except Exception:
                count = 1

        results = []
        for i in range(count):
            one = _run_scheduler_once(system)
            results.append({
                "tick_index": i + 1,
                "result": one,
            })
        print_json({
            "ok": True,
            "count": count,
            "results": results,
        })
        return

    if text.startswith("/task_submit_retry ") or text.startswith("/retrytask "):
        parsed = _parse_retry_command(text)
        if not parsed:
            print("用法: /task_submit_retry <max_retries> <retry_delay> <goal>")
            print("或:   /retrytask <max_retries> <retry_delay> <goal>")
            return

        submit_and_run(
            system,
            parsed["goal"],
            max_retries=parsed["max_retries"],
            retry_delay=parsed["retry_delay"],
        )
        return

    if text.startswith("/task_create_retry "):
        parsed = _parse_retry_command(text)
        if not parsed:
            print("用法: /task_create_retry <max_retries> <retry_delay> <goal>")
            return

        create_task_only(
            system,
            parsed["goal"],
            max_retries=parsed["max_retries"],
            retry_delay=parsed["retry_delay"],
        )
        return

    if text.startswith("/task_submit "):
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            print("用法: /task_submit <goal>")
            return
        submit_and_run(system, parts[1].strip())
        return

    if text.startswith("/task_create "):
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            print("用法: /task_create <goal>")
            return
        create_task_only(system, parts[1].strip())
        return

    if text.startswith("/task_show "):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            print("缺少 task_name")
            return
        print_json(system.get_task(parts[1].strip()))
        return

    if text.startswith("/task "):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            print("缺少 task_name")
            return
        print_json(system.get_task(parts[1].strip()))
        return

    if text.startswith("/task_pause "):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            print("缺少 task_name")
            return
        print_json(system.pause_task(parts[1].strip()))
        return

    if text.startswith("/pause "):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            print("缺少 task_name")
            return
        print_json(system.pause_task(parts[1].strip()))
        return

    if text.startswith("/task_resume "):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            print("缺少 task_name")
            return
        print_json(system.resume_task(parts[1].strip()))
        return

    if text.startswith("/resume "):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            print("缺少 task_name")
            return
        print_json(system.resume_task(parts[1].strip()))
        return

    if text.startswith("/task_cancel "):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            print("缺少 task_name")
            return
        print_json(system.cancel_task(parts[1].strip()))
        return

    if text.startswith("/cancel "):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            print("缺少 task_name")
            return
        print_json(system.cancel_task(parts[1].strip()))
        return

    if text.startswith("/task_priority "):
        parts = text.split()
        if len(parts) < 3:
            print("用法: /task_priority <task_name> <number>")
            return
        task_name = parts[1].strip()
        try:
            priority = int(parts[2])
        except Exception:
            print("priority 必須是整數")
            return
        print_json(system.set_task_priority(task_name, priority))
        return

    if text.startswith("/priority "):
        parts = text.split()
        if len(parts) < 3:
            print("用法: /priority <task_name> <number>")
            return
        task_name = parts[1].strip()
        try:
            priority = int(parts[2])
        except Exception:
            print("priority 必須是整數")
            return
        print_json(system.set_task_priority(task_name, priority))
        return

    print("未知指令，輸入 /help 查看說明。")


def handle_natural_input(system: Any, text: str) -> None:
    submit_and_run(system, text)


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

        if text in ("/exit", "/quit"):
            print("已離開。")
            break

        if text.startswith("/"):
            handle_command(system, text)
            continue

        handle_natural_input(system, text)


if __name__ == "__main__":
    main()