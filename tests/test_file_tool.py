from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.tools.file_tool import FileTool


def print_block(title: str, data: dict) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    pprint(data, sort_dicts=False)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    workspace_root = "workspace"
    test_dir = "file_tool_smoke"
    test_file = f"{test_dir}/hello.txt"

    tool = FileTool(workspace_dir=workspace_root)
    workspace_path = Path(tool.workspace_root)

    print("\n[FileTool Smoke Test]")
    print(f"project_root   = {PROJECT_ROOT}")
    print(f"workspace_root = {workspace_path}")

    cleanup_target = workspace_path / test_file
    if cleanup_target.exists():
        cleanup_target.unlink()

    cleanup_dir = workspace_path / test_dir
    if cleanup_dir.exists() and cleanup_dir.is_dir():
        pass

    result_exists_before = tool.execute({
        "action": "exists",
        "path": test_file,
    })
    print_block("1. exists before write", result_exists_before)

    assert_true(result_exists_before["ok"] is True, "exists before write should succeed")
    exists_before = result_exists_before["results"][0]["exists"]
    assert_true(exists_before is False, "file should not exist before write")

    result_write = tool.execute({
        "action": "write",
        "path": test_file,
        "content": "第一行內容",
    })
    print_block("2. write", result_write)

    assert_true(result_write["ok"] is True, "write should succeed")
    expected_file_path = workspace_path / test_file
    assert_true(expected_file_path.exists(), "written file should exist on disk")

    result_read = tool.execute({
        "action": "read",
        "path": test_file,
    })
    print_block("3. read", result_read)

    assert_true(result_read["ok"] is True, "read should succeed")
    read_content = result_read["results"][0]["content"]
    assert_true(read_content == "第一行內容", "read content mismatch after write")

    result_append = tool.execute({
        "action": "append",
        "path": test_file,
        "content": "\n第二行內容",
    })
    print_block("4. append", result_append)

    assert_true(result_append["ok"] is True, "append should succeed")

    result_read_after_append = tool.execute({
        "action": "read",
        "path": test_file,
    })
    print_block("5. read after append", result_read_after_append)

    assert_true(result_read_after_append["ok"] is True, "read after append should succeed")
    appended_content = result_read_after_append["results"][0]["content"]
    assert_true(
        appended_content == "第一行內容\n第二行內容",
        "content mismatch after append",
    )

    result_overwrite = tool.execute({
        "action": "overwrite",
        "path": test_file,
        "content": "覆寫後的新內容",
    })
    print_block("6. overwrite", result_overwrite)

    assert_true(result_overwrite["ok"] is True, "overwrite should succeed")

    result_read_again = tool.execute({
        "action": "read",
        "path": test_file,
    })
    print_block("7. read after overwrite", result_read_again)

    assert_true(result_read_again["ok"] is True, "read after overwrite should succeed")
    overwritten_content = result_read_again["results"][0]["content"]
    assert_true(overwritten_content == "覆寫後的新內容", "overwrite content mismatch")

    result_dirty = tool.execute({
        "action": "exists",
        "path": "workspace/workspace/file_tool_smoke/hello.txt",
    })
    print_block("8. dirty path test", result_dirty)

    assert_true("ok" in result_dirty, "dirty path result should have ok field")
    assert_true("error" in result_dirty, "dirty path result should have error field")

    result_escape = tool.execute({
        "action": "read",
        "path": "../../Windows/system.ini",
    })
    print_block("9. escape path test", result_escape)

    assert_true(result_escape["ok"] is False, "escape path should fail")
    assert_true(result_escape["error"] is not None, "escape path should return structured error")

    print("\n" + "=" * 80)
    print("驗收結論")
    print("=" * 80)
    print("1. exists / write / read / append / overwrite 都已走通")
    print("2. 實際檔案位置應在 workspace/file_tool_smoke/hello.txt")
    print("3. escape path 應失敗，不能跳出 workspace")
    print("4. 每一步都應維持固定 dict 結構")
    print("\nPASS: test_file_tool.py")


if __name__ == "__main__":
    main()