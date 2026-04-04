from __future__ import annotations

import json
from pathlib import Path

from core.tools.tool_registry import ToolRegistry
from core.runtime.step_executor import StepExecutor


def print_block(title: str, data):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    if isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(data)


def main():
    workspace_dir = "workspace"

    print_block("START", f"workspace_dir = {workspace_dir}")

    tool_registry = ToolRegistry(workspace_dir=workspace_dir)
    step_executor = StepExecutor(
        tool_registry=tool_registry,
        workspace_root=workspace_dir,
        debug=True,
    )

    print_block("REGISTERED TOOLS", tool_registry.list_tools())

    steps = [
        {
            "type": "write_file",
            "path": "hello.py",
            "content": "print('hello ZERO from command tool')",
        },
        {
            "type": "command",
            "command": "python hello.py",
        },
        {
            "type": "respond",
            "message": "step chain finished",
        },
    ]

    result = step_executor.execute_steps(steps)

    print_block("EXECUTE_STEPS RESULT", result)

    hello_file = Path(workspace_dir) / "hello.py"
    print_block("FILE EXISTS", hello_file.exists())

    if hello_file.exists():
        print_block("FILE CONTENT", hello_file.read_text(encoding="utf-8"))

    # 額外檢查 command step 的 stdout
    if isinstance(result, dict):
        results = result.get("results", [])
        if len(results) >= 2:
            command_result = results[1]
            print_block("COMMAND STEP RESULT", command_result)

            inner = command_result.get("result", {})
            stdout = inner.get("stdout")
            stderr = inner.get("stderr")
            return_code = inner.get("return_code", inner.get("returncode"))

            print_block("COMMAND STDOUT", stdout)
            print_block("COMMAND STDERR", stderr)
            print_block("COMMAND RETURN CODE", return_code)

    print("\nDONE")


if __name__ == "__main__":
    main()