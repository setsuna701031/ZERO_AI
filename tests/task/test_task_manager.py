from core.task_manager import TaskManager
from core.task.task_models import StepRecord


def main():
    manager = TaskManager("workspace")

    task = manager.create_task(
        task_id="task_manager_test",
        title="測試 TaskManager",
        goal="測試任務流程"
    )

    step1 = StepRecord(
        step_id="step_1",
        title="建立資料夾",
        tool="workspace",
        input_data={"action": "mkdir", "path": "demo"}
    )

    manager.add_step(task, step1)

    manager.transition_status(task, "planning", "start planning")
    manager.transition_status(task, "running", "start running")

    manager.start_step(task, 0)
    manager.complete_step(task, 0, {"ok": True})

    manager.complete_task(task, {"result": "done"})

    print("Task finished.")
    print(manager.load_task("task_manager_test").to_dict())


if __name__ == "__main__":
    main()