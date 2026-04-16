from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.tools.tool_registry import ToolRegistry


def print_block(title: str, data: dict) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    pprint(data, sort_dicts=False)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    registry = ToolRegistry()

    print("\n[ToolRegistry Smoke Test]")
    print(f"project_root = {PROJECT_ROOT}")

    workspace_root = PROJECT_ROOT / "workspace"
    registry_file_path = workspace_root / "registry_smoke" / "hello.txt"
    registry_ws_path = workspace_root / "shared" / "registry_ws" / "hello.txt"

    if registry_file_path.exists():
        registry_file_path.unlink()

    if registry_ws_path.exists():
        registry_ws_path.unlink()

    # 1. list tools
    result_list = registry.list_tools()
    print_block("1. list_tools", result_list)

    assert_true(result_list["ok"] is True, "list_tools should succeed")
    assert_true(result_list["count"] >= 4, "expected at least 4 registered tools")

    tool_names = {entry["name"] for entry in result_list["tools"]}
    assert_true("command" in tool_names, "command tool should be registered")
    assert_true("file" in tool_names, "file tool should be registered")
    assert_true("workspace" in tool_names, "workspace tool should be registered")
    assert_true("web_search" in tool_names, "web_search tool should be registered")

    # 2. alias resolve
    assert_true(registry.has_tool("command_tool") is True, "command_tool alias should resolve")
    assert_true(registry.has_tool("workspace_tool") is True, "workspace_tool alias should resolve")
    assert_true(registry.has_tool("file_tool") is True, "file_tool alias should resolve")
    assert_true(registry.has_tool("search_web") is True, "search_web alias should resolve")

    print("\nAlias resolve check: PASS")

    # 3. tool not found
    result_missing = registry.execute_tool("not_exists", {})
    print_block("3. execute_tool(not_exists)", result_missing)

    assert_true(result_missing["ok"] is False, "missing tool should fail")
    assert_true(result_missing["error"] is not None, "missing tool should return structured error")
    assert_true(result_missing["error"]["type"] == "tool_not_found", "missing tool error type mismatch")

    # 4. command success
    result_command = registry.execute_tool("command", {"command": "echo registry_ok"})
    print_block("4. execute_tool(command)", result_command)

    assert_true(result_command["ok"] is True, "registry command call should succeed")
    assert_true(result_command["output"]["ok"] is True, "command output ok should be true")
    assert_true("registry_ok" in result_command["output"]["stdout"], "command stdout mismatch")

    # 5. file success through registry
    result_file_write = registry.execute_tool(
        "file",
        {
            "action": "write",
            "path": "registry_smoke/hello.txt",
            "content": "registry file ok",
        },
    )
    print_block("5. execute_tool(file write)", result_file_write)

    assert_true(result_file_write["ok"] is True, "registry file write should succeed")
    assert_true(result_file_write["output"]["ok"] is True, "file tool output ok should be true")

    result_file_read = registry.execute_tool(
        "file",
        {
            "action": "read",
            "path": "registry_smoke/hello.txt",
        },
    )
    print_block("6. execute_tool(file read)", result_file_read)

    assert_true(result_file_read["ok"] is True, "registry file read should succeed")
    assert_true(
        result_file_read["output"]["results"][0]["content"] == "registry file ok",
        "registry file read content mismatch",
    )

    # 6. workspace success through registry
    result_workspace_write = registry.execute_tool(
        "workspace",
        {
            "action": "write",
            "path": "registry_ws/hello.txt",
            "content": "registry workspace ok",
        },
    )
    print_block("7. execute_tool(workspace write)", result_workspace_write)

    assert_true(result_workspace_write["ok"] is True, "registry workspace write should succeed")
    assert_true(result_workspace_write["output"]["ok"] is True, "workspace tool output ok should be true")

    result_workspace_read = registry.execute_tool(
        "workspace",
        {
            "action": "read",
            "path": "registry_ws/hello.txt",
        },
    )
    print_block("8. execute_tool(workspace read)", result_workspace_read)

    assert_true(result_workspace_read["ok"] is True, "registry workspace read should succeed")
    assert_true(
        result_workspace_read["output"]["content"] == "registry workspace ok",
        "registry workspace read content mismatch",
    )

    print("\n" + "=" * 80)
    print("驗收結論")
    print("=" * 80)
    print("1. registry list_tools 正常")
    print("2. alias resolve 正常")
    print("3. tool_not_found 錯誤格式固定")
    print("4. registry -> command 正常")
    print("5. registry -> file 正常")
    print("6. registry -> workspace 正常")
    print("\nPASS: test_tool_registry.py")


if __name__ == "__main__":
    main()