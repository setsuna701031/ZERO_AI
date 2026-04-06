from core.tasks.task_repository import TaskRepository


def print_tasks(title: str, repo: TaskRepository) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    tasks = repo.list_tasks()
    for task in tasks:
        print(
            f"task_id={task.get('task_id')}, "
            f"status={task.get('status')}, "
            f"depends_on={task.get('depends_on')}, "
            f"history={task.get('history')}"
        )
    if not tasks:
        print("(no tasks)")


def main() -> None:
    repo = TaskRepository(db_path="workspace/tasks.json")

    # 測試前先清空
    repo.tasks = []
    repo.save()

    print_tasks("初始狀態", repo)

    # 1. 建立無依賴任務 -> 應該 queued
    repo.create_task(
        task_id="task_a",
        goal="first task",
        title="Task A",
    )

    print_tasks("建立 task_a 後（預期 task_a = queued）", repo)

    # 2. 建立有依賴任務 -> 應該 blocked
    repo.create_task(
        task_id="task_b",
        goal="second task",
        title="Task B",
        depends_on=["task_a"],
    )

    print_tasks("建立 task_b 後（預期 task_b = blocked）", repo)

    # 3. 看 ready tasks -> 只應該有 task_a
    ready_1 = repo.get_ready_tasks()
    print("\nready tasks #1")
    for task in ready_1:
        print(f"{task['task_id']} -> {task['status']}")

    # 4. 把 task_a 改成 done
    task_a = repo.get_task("task_a")
    if task_a is None:
        raise RuntimeError("task_a not found")

    task_a["status"] = "done"
    task_a["history"] = ["queued", "done"]
    repo.upsert_task(task_a)

    print_tasks("把 task_a 改成 done 後", repo)

    # 5. 再看 ready tasks -> 應該有 task_b
    ready_2 = repo.get_ready_tasks()
    print("\nready tasks #2")
    for task in ready_2:
        print(f"{task['task_id']} -> {task['status']}")

    print_tasks("最終狀態（預期 task_b 變 queued）", repo)


if __name__ == "__main__":
    main()