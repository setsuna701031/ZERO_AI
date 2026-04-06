from core.tasks.task_repository import TaskRepository


def print_tasks(repo):
    tasks = repo.list_tasks()
    print("\n==== TASK LIST ====")
    for t in tasks:
        print(
            t["task_id"],
            t["status"],
            "depends_on=",
            t["depends_on"],
        )


def main():
    repo = TaskRepository(db_path="workspace/tasks.json")

    # reset
    repo.tasks = []
    repo.save()

    repo.create_task(
        task_id="task_a",
        goal="first task",
    )

    repo.create_task(
        task_id="task_b",
        goal="second task",
        depends_on=["task_a"],
    )

    print_tasks(repo)

    print("\n==== READY TASKS #1 ====")
    for t in repo.get_ready_tasks():
        print(t["task_id"], t["status"])

    # 故意模擬 runtime 用 finished 而不是 done
    task_a = repo.get_task("task_a")
    if task_a is None:
        raise RuntimeError("task_a not found")

    task_a["status"] = "finished"
    task_a["history"].append("finished")
    repo.upsert_task(task_a)

    print("\n==== AFTER task_a FINISHED ====")
    print_tasks(repo)

    print("\n==== READY TASKS #2 ====")
    for t in repo.get_ready_tasks():
        print(t["task_id"], t["status"])


if __name__ == "__main__":
    main()