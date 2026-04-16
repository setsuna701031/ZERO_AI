from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.tools.workspace_tool import WorkspaceTool


def print_block(title: str, data: dict) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    pprint(data, sort_dicts=False)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    tool = WorkspaceTool(workspace_dir="workspace")
    workspace_root = Path(tool.workspace_root)

    test_file = "ws_smoke/hello_ws.txt"
    test_dir = "ws_smoke"

    print("\n[WorkspaceTool Smoke Test]")
    print(f"project_root   = {PROJECT_ROOT}")
    print(f"workspace_root = {workspace_root}")

    target_file = workspace_root / "shared" / "ws_smoke" / "hello_ws.txt"
    if target_file.exists():
        target_file.unlink()

    # 1. write without task_id -> should go to shared
    result_write = tool.execute({
        "action": "write",
        "path": test_file,
        "content": "hello workspace",
    })
    print_block("1. write without task_id", result_write)

    assert_true(result_write["ok"] is True, "write without task_id should succeed")
    assert_true(target_file.exists(), "workspace write should land in shared path")

    # 2. read without task_id <- should read from shared
    result_read = tool.execute({
        "action": "read",
        "path": test_file,
    })
    print_block("2. read without task_id", result_read)

    assert_true(result_read["ok"] is True, "read without task_id should succeed")
    read_content = result_read["content"]
    assert_true(read_content == "hello workspace", "workspace read content mismatch")

    # 3. append without task_id
    result_append = tool.execute({
        "action": "append",
        "path": test_file,
        "content": "\nsecond line",
    })
    print_block("3. append without task_id", result_append)

    assert_true(result_append["ok"] is True, "append without task_id should succeed")

    # 4. read after append
    result_read_after_append = tool.execute({
        "action": "read",
        "path": test_file,
    })
    print_block("4. read after append", result_read_after_append)

    assert_true(result_read_after_append["ok"] is True, "read after append should succeed")
    appended_content = result_read_after_append["content"]
    assert_true(
        appended_content == "hello workspace\nsecond line",
        "workspace append content mismatch",
    )

    # 5. exists
    result_exists = tool.execute({
        "action": "exists",
        "path": test_file,
    })
    print_block("5. exists", result_exists)

    assert_true(result_exists["ok"] is True, "exists should succeed")
    exists_info = result_exists["results"][0]
    assert_true(exists_info["exists"] is True, "workspace file should exist")
    assert_true(exists_info["is_file"] is True, "workspace target should be file")

    # 6. mkdir without task_id -> should go to shared
    result_mkdir = tool.execute({
        "action": "mkdir",
        "path": "ws_smoke/subdir",
    })
    print_block("6. mkdir without task_id", result_mkdir)

    assert_true(result_mkdir["ok"] is True, "mkdir without task_id should succeed")
    expected_dir = workspace_root / "shared" / "ws_smoke" / "subdir"
    assert_true(expected_dir.exists(), "workspace mkdir should land in shared path")
    assert_true(expected_dir.is_dir(), "created path should be directory")

    # 7. list workspace root
    result_list_root = tool.execute({
        "action": "list",
        "path": ".",
        "recursive": False,
    })
    print_block("7. list workspace root", result_list_root)

    assert_true(result_list_root["ok"] is True, "list workspace root should succeed")
    assert_true(result_list_root["count"] >= 1, "workspace root should have at least one item")

    # 8. list shared/ws_smoke
    result_list_test_dir = tool.execute({
        "action": "list",
        "path": "shared/ws_smoke",
        "recursive": False,
    })
    print_block("8. list shared/ws_smoke", result_list_test_dir)

    assert_true(result_list_test_dir["ok"] is True, "list shared/ws_smoke should succeed")
    item_names = {item["name"] for item in result_list_test_dir["items"]}
    assert_true("hello_ws.txt" in item_names, "list should contain hello_ws.txt")
    assert_true("subdir" in item_names, "list should contain subdir")

    # 9. invalid action
    result_invalid = tool.execute({
        "action": "not_real_action",
        "path": test_file,
    })
    print_block("9. invalid action", result_invalid)

    assert_true(result_invalid["ok"] is False, "invalid action should fail")
    assert_true(result_invalid["error"] is not None, "invalid action should return structured error")

    print("\n" + "=" * 80)
    print("驗收結論")
    print("=" * 80)
    print("1. 無 task_id 時 write/read/append/mkdir 預設走 shared")
    print("2. list '.' 可正常列出 workspace root")
    print("3. list 'shared/ws_smoke' 可正常列出測試目錄")
    print("4. invalid action 會回固定 error 結構")
    print("\nPASS: test_workspace_tool.py")


if __name__ == "__main__":
    main()