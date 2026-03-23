from tools.file_tool import FileTool


def print_block(title: str, data: dict) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    for k, v in data.items():
        print(f"{k}: {v}")


def main() -> None:
    tool = FileTool(workspace_root="E:/zero_ai")

    # 1. mkdir
    result_mkdir = tool.execute({
        "action": "mkdir",
        "path": "task_0007/test_area"
    })
    print_block("1. mkdir", result_mkdir)

    # 2. write
    result_write = tool.execute({
        "action": "write",
        "path": "task_0007/test_area/hello.txt",
        "content": "第一行內容"
    })
    print_block("2. write", result_write)

    # 3. read
    result_read = tool.execute({
        "action": "read",
        "path": "task_0007/test_area/hello.txt"
    })
    print_block("3. read", result_read)

    # 4. append
    result_append = tool.execute({
        "action": "append",
        "path": "task_0007/test_area/hello.txt",
        "content": "\n第二行內容"
    })
    print_block("4. append", result_append)

    # 5. overwrite
    result_overwrite = tool.execute({
        "action": "overwrite",
        "path": "task_0007/test_area/hello.txt",
        "content": "覆寫後的新內容"
    })
    print_block("5. overwrite", result_overwrite)

    # 6. exists
    result_exists = tool.execute({
        "action": "exists",
        "path": "task_0007/test_area/hello.txt"
    })
    print_block("6. exists", result_exists)

    # 7. read again
    result_read_again = tool.execute({
        "action": "read",
        "path": "task_0007/test_area/hello.txt"
    })
    print_block("7. read again", result_read_again)

    # 8. dirty path test
    result_dirty = tool.execute({
        "action": "exists",
        "path": "workspace/workspace/task_0007/test_area/hello.txt"
    })
    print_block("8. dirty path test", result_dirty)

    # 9. escape test
    result_escape = tool.execute({
        "action": "read",
        "path": "../../Windows/system.ini"
    })
    print_block("9. escape test", result_escape)

    print("\n" + "=" * 60)
    print("檢查重點")
    print("=" * 60)
    print("1. hello.txt 的實際位置應該是：")
    print("   E:/zero_ai/workspace/task_0007/test_area/hello.txt")
    print("2. 不應該出現 workspace/workspace")
    print("3. dirty path test 應該仍能正確解析到同一個檔案")
    print("4. escape test 應該失敗，不能跳出 workspace")


if __name__ == "__main__":
    main()