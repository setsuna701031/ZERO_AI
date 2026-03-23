from __future__ import annotations

from typing import Any, Dict, Iterable

from services.system_boot import bootstrap_system


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _print_banner() -> None:
    print("=" * 60)
    print("ZERO AI")
    print("Runtime Task Mode")
    print("=" * 60)


def _print_boot_info(boot_info: Dict[str, Any]) -> None:
    print("[boot]")
    print(f"project_root   : {_safe_str(boot_info.get('project_root'))}")
    print(f"workspace_root : {_safe_str(boot_info.get('workspace_root'))}")
    print(f"agent_loop     : {_safe_str(boot_info.get('agent_loop_name'))}")
    print(f"task_manager   : {_safe_str(boot_info.get('task_manager_name'))}")
    print(f"task_runtime   : {_safe_str(boot_info.get('task_runtime_name'))}")

    tool_names = boot_info.get("tool_names", [])
    if isinstance(tool_names, list) and tool_names:
        print(f"tools          : {', '.join(_safe_str(x) for x in tool_names)}")
    else:
        print("tools          : (none)")

    print("-" * 60)
    print("輸入一般文字 -> 建立任務並執行")
    print("cmd:你的指令  -> 執行 command_tool")
    print("ws:檔案路徑   -> 執行 workspace_tool 讀檔")
    print("exit          -> 離開")
    print("=" * 60)


def _print_error(result: Dict[str, Any]) -> None:
    summary = _safe_str(result.get("summary", "Execution failed."))
    error = _safe_str(result.get("error", ""))

    print(f"[failed] {summary}")
    if error:
        print(f"[error] {error}")


def _print_key_value(key: str, value: Any, width: int = 11) -> None:
    print(f"{key:<{width}}: {_safe_str(value)}")


def _print_multiline_value(key: str, value: str, width: int = 11) -> None:
    lines = str(value).splitlines()
    if not lines:
        print(f"{key:<{width}}: ")
        return

    print(f"{key:<{width}}: {lines[0]}")
    for line in lines[1:]:
        print(" " * (width + 2) + line)


def _print_list_block(key: str, items: Iterable[Any], width: int = 11) -> None:
    items = list(items)
    if not items:
        print(f"{key:<{width}}: []")
        return

    print(f"{key:<{width}}:")
    for item in items:
        print(f"{' ' * (width + 2)}- {_safe_str(item)}")


def _print_tool_result(result: Dict[str, Any]) -> None:
    data = result.get("data", {})
    tool_name = _safe_str(data.get("tool_name", ""))
    tool_result = data.get("tool_result", {})

    print(f"[tool] {tool_name}")

    if isinstance(tool_result, dict):
        for key, value in tool_result.items():
            if isinstance(value, list):
                _print_list_block(key, value)
            elif isinstance(value, str) and "\n" in value:
                _print_multiline_value(key, value)
            else:
                _print_key_value(key, value)
    else:
        print(_safe_str(tool_result))


def _print_runtime_result(result: Dict[str, Any]) -> None:
    summary = _safe_str(result.get("summary", "Task executed."))
    data = result.get("data", {})

    task = data.get("task", {})
    runtime_result = data.get("runtime_result", {})

    print(f"[ok] {summary}")
    print("-" * 60)

    if isinstance(task, dict) and task:
        print("[task]")

        ordered_task_keys = [
            "task_name",
            "goal",
            "input",
            "status",
            "task_dir",
            "created_at",
            "updated_at",
        ]

        printed_task_keys = set()

        for key in ordered_task_keys:
            if key in task:
                _print_key_value(key, task.get(key))
                printed_task_keys.add(key)

        for key, value in task.items():
            if key not in printed_task_keys:
                if isinstance(value, list):
                    _print_list_block(key, value)
                elif isinstance(value, str) and "\n" in value:
                    _print_multiline_value(key, value)
                else:
                    _print_key_value(key, value)

    if isinstance(runtime_result, dict) and runtime_result:
        print("[runtime]")

        ordered_runtime_keys = [
            "task_name",
            "task_dir",
            "status",
            "plan_file",
            "result_file",
            "log_file",
            "step_count",
            "answer",
        ]

        printed_runtime_keys = set()

        for key in ordered_runtime_keys:
            if key in runtime_result:
                _print_key_value(key, runtime_result.get(key))
                printed_runtime_keys.add(key)

        if "step_files" in runtime_result:
            _print_list_block("step_files", runtime_result.get("step_files", []))
            printed_runtime_keys.add("step_files")

        if "step_file" in runtime_result:
            _print_key_value("step_file", runtime_result.get("step_file"))
            printed_runtime_keys.add("step_file")

        for key, value in runtime_result.items():
            if key not in printed_runtime_keys:
                if isinstance(value, list):
                    _print_list_block(key, value)
                elif isinstance(value, str) and "\n" in value:
                    _print_multiline_value(key, value)
                else:
                    _print_key_value(key, value)

    print("-" * 60)


def _print_result(result: Dict[str, Any]) -> None:
    if not isinstance(result, dict):
        print(_safe_str(result))
        return

    success = bool(result.get("success", False))
    mode = _safe_str(result.get("mode", ""))

    if not success:
        _print_error(result)
        return

    if mode == "tool":
        _print_tool_result(result)
        return

    if mode in {"runtime", "task"}:
        _print_runtime_result(result)
        return

    summary = _safe_str(result.get("summary", "Done."))
    print(summary)

    data = result.get("data", {})
    if isinstance(data, dict) and data:
        for key, value in data.items():
            if isinstance(value, list):
                _print_list_block(key, value)
            elif isinstance(value, str) and "\n" in value:
                _print_multiline_value(key, value)
            else:
                _print_key_value(key, value)


def main() -> None:
    system = bootstrap_system()
    agent = system["agent"]
    boot_info = system["boot_info"]

    _print_banner()
    _print_boot_info(boot_info)

    while True:
        try:
            user_input = input("\nZERO> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nbye.")
            break

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit"}:
            print("bye.")
            break

        try:
            result = agent.run(user_input)
        except KeyboardInterrupt:
            print("\n[interrupted]")
            continue
        except Exception as exc:
            print(f"[fatal] {exc}")
            continue

        _print_result(result)


if __name__ == "__main__":
    main()