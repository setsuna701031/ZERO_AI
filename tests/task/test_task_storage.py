from core.task.task_models import TaskRecord, StepRecord
from core.task.task_storage import TaskStorage


def main():
    workspace_root = "workspace"
    storage = TaskStorage(workspace_root)

    step = StepRecord(
        step_id="step_1",
        title="建立資料夾",
        tool="workspace",
        input_data={"action": "mkdir", "path": "demo"}
    )

    task = TaskRecord(
        task_id="task_test_001",
        title="測試儲存任務",
        goal="測試 task storage",
        steps=[step]
    )

    print("Saving task...")
    storage.save_task(task)

    print("Loading task...")
    loaded = storage.load_task("task_test_001")

    if loaded:
        print("Loaded task:")
        print(loaded.to_dict())
    else:
        print("Task not found")

    print("All tasks:")
    print(storage.list_tasks())


if __name__ == "__main__":
    main()