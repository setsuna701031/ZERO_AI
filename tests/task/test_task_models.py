from core.task.task_models import TaskRecord, StepRecord


def main():
    step1 = StepRecord(
        step_id="step_1",
        title="建立資料夾",
        description="建立專案資料夾",
        tool="workspace",
        input_data={"action": "mkdir", "path": "demo"}
    )

    task = TaskRecord(
        task_id="task_001",
        title="測試任務",
        goal="測試 task models",
        steps=[step1]
    )

    data = task.to_dict()
    print("Task to_dict:")
    print(data)

    task2 = TaskRecord.from_dict(data)
    print("\nLoaded Task:")
    print(task2.to_dict())


if __name__ == "__main__":
    main()