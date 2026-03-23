from tools.workspace_tool import WorkspaceTool


def print_block(title: str, data: dict) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    for k, v in data.items():
        print(f"{k}: {v}")


def main() -> None:
    tool = WorkspaceTool()

    # 1. create_task
    result_create = tool.execute({
        "action": "create_task",
        "task_name": "測試 path manager",
        "description": "檢查 workspace 路徑是否正常"
    })
    print_block("1. create_task", result_create)

    if not result_create.get("ok"):
        print("\ncreate_task 失敗，停止測試。")
        return

    task_id = result_create.get("task_id", "")
    task_dir = result_create.get("task_dir", "")

    print(f"\n建立出的 task_id = {task_id}")
    print(f"建立出的 task_dir = {task_dir}")

    # 2. get_task_path
    result_path = tool.execute({
        "action": "get_task_path",
        "task_id": task_id
    })
    print_block("2. get_task_path", result_path)

    # 3. write_note
    result_note = tool.execute({
        "action": "write_note",
        "task_id": task_id,
        "text": "這是一筆測試筆記。"
    })
    print_block("3. write_note", result_note)

    # 4. write_plan
    result_plan = tool.execute({
        "action": "write_plan",
        "task_id": task_id,
        "text": "Step 1: 測試 create_task\nStep 2: 測試 write_note\nStep 3: 測試 write_plan"
    })
    print_block("4. write_plan", result_plan)

    # 5. get_task
    result_get = tool.execute({
        "action": "get_task",
        "task_id": task_id
    })
    print_block("5. get_task", result_get)

    print("\n" + "=" * 60)
    print("檢查重點")
    print("=" * 60)
    print("1. task_dir 裡面不能出現 workspace/workspace")
    print("2. notes_path / plan_path 不能出現 workspace/workspace")
    print("3. 實體資料夾應該存在：")
    print(f"   {task_dir}")
    print("4. 裡面應該有這些檔案：")
    print("   - plan.txt")
    print("   - notes.txt")
    print("   - logs.txt")
    print("   - task.json")
    print("   - files/")
    print("   - output/")


if __name__ == "__main__":
    main()