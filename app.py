from __future__ import annotations

import json
import os
from typing import Any, Dict

from services.system_boot import boot_system


WORKSPACE_DIR = os.environ.get("ZERO_WORKSPACE", "workspace")


def print_help() -> None:
    print("可用指令：")
    print("  /help                          顯示說明")
    print("  /health                        系統健康狀態")
    print("  /tools                         顯示目前已註冊工具")
    print("  /executor                      顯示 step_executor 物件資訊")
    print("  /queue                         顯示任務佇列")
    print("  /tasks                         顯示任務快照")
    print("  /task <task_name>              顯示單一任務")
    print("  /tick                          執行一次 scheduler tick")
    print("  /run <count>                   連續執行多次 tick")
    print("  /pause <task_name>             暫停任務")
    print("  /resume <task_name>            恢復任務")
    print("  /cancel <task_name>            取消任務")
    print("  /priority <task> <num>         設定任務優先級")
    print("")
    print("Task OS 別名指令：")
    print("  /task_submit <goal>            建立任務並立刻執行一次")
    print("  /task_create <goal>            只建立任務，不立刻 tick")
    print("  /task_list                     顯示任務佇列")
    print("  /task_tasks                    顯示任務快照")
    print("  /task_show <task_name>         顯示單一任務")
    print("  /task_tick                     執行一次 scheduler tick")
    print("  /task_run <count>              連續執行多次 tick")
    print("  /task_pause <task_name>        暫停任務")
    print("  /task_resume <task_name>       恢復任務")
    print("  /task_cancel <task_name>       取消任務")
    print("  /task_priority <task> <num>    設定任務優先級")
    print("")
    print("  其他自然語言輸入會直接建立任務並立刻執行一次")
    print("  /exit                          離開")
    print("  /quit                          離開")


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
        return

    summary = summarize_tool_result(result)
    if summary:
        print("[result]")
        print(summary)


def print_task_result(submit_result: Dict[str, Any], tick_result: Dict[str, Any], system: Any) -> None:
    task_name = submit_result.get("task_name", "")
    print(f"[task] {task_name}")

    if tick_result.get("ok"):
        final_answer = tick_result.get("final_answer")
        if final_answer:
            print(final_answer)

        execution_log = tick_result.get("execution_log")
        if isinstance(execution_log, list) and execution_log:
            print_execution_log(execution_log)
            return

        task_result = system.get_task(task_name)
        if task_result.get("ok"):
            task = task_result.get("task", {})
            task_final_answer = task.get("final_answer")
            if task_final_answer and task_final_answer != tick_result.get("final_answer"):
                print(task_final_answer)

            task_log = task.get("execution_log", [])
            if isinstance(task_log, list) and task_log:
                print_execution_log(task_log)
                return

        message = tick_result.get("message")
        if message and not final_answer:
            print(message)
        return

    print("[tick_failed]")
    print_json(tick_result)

    task_result = system.get_task(task_name)
    if task_result.get("ok"):
        task = task_result.get("task", {})
        final_answer = task.get("final_answer")
        if final_answer:
            print(final_answer)
        task_log = task.get("execution_log", [])
        if isinstance(task_log, list) and task_log:
            print_execution_log(task_log)


def submit_and_tick(system: Any, goal: str) -> None:
    submit_result = system.submit_task(goal=goal)

    if not submit_result.get("ok"):
        print_json(submit_result)
        return

    tick_result = system.tick()
    print_task_result(submit_result, tick_result, system)


def create_task_only(system: Any, goal: str) -> None:
    submit_result = system.submit_task(goal=goal)
    print_json(submit_result)


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
        print_json(system.tick())
        return

    if text.startswith("/run") or text.startswith("/task_run"):
        parts = text.split()
        count = 1
        if len(parts) >= 2:
            try:
                count = int(parts[1])
            except Exception:
                count = 1
        print_json(system.run(count))
        return

    if text.startswith("/task_submit "):
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            print("用法: /task_submit <goal>")
            return
        submit_and_tick(system, parts[1].strip())
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
    submit_and_tick(system, text)


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