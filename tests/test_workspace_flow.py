import importlib
from typing import Any

from core.tasks.task_workspace import TaskWorkspace
from core.runtime.task_runtime import TaskRuntime
from core.planning.planner import Planner
from core.runtime.step_executor import StepExecutor


def load_scheduler_class() -> Any:
    """
    安全載入 scheduler 類：
    1. 先找 core.tasks.scheduler.Scheduler
    2. 沒有的話找 core.tasks.scheduler.TaskScheduler
    3. 都沒有就直接報錯
    """
    module = importlib.import_module("core.tasks.scheduler")

    if hasattr(module, "Scheduler"):
        return getattr(module, "Scheduler")

    if hasattr(module, "TaskScheduler"):
        return getattr(module, "TaskScheduler")

    raise ImportError(
        "core.tasks.scheduler 裡找不到 Scheduler 或 TaskScheduler 類別，"
        "請檢查你目前本地的 scheduler.py 類名。"
    )


def build_scheduler(planner, executor, runtime):
    SchedulerClass = load_scheduler_class()

    # 盡量兼容不同 __init__ 寫法
    for kwargs in (
        {
            "planner": planner,
            "step_executor": executor,
            "runtime": runtime,
        },
        {
            "planner": planner,
            "step_executor": executor,
            "runtime_store": runtime,
        },
        {
            "planner": planner,
            "step_executor": executor,
        },
        {},
    ):
        try:
            return SchedulerClass(**kwargs)
        except TypeError:
            continue

    raise RuntimeError("無法建立 scheduler，__init__ 參數不相容。")


def main():
    workspace = TaskWorkspace()
    runtime = TaskRuntime()
    planner = Planner()
    executor = StepExecutor()

    scheduler = build_scheduler(planner, executor, runtime)

    task = {
        "id": "task_workspace_test_001",
        "task_name": "task_workspace_test_001",
        "title": "workspace test",
        "goal": "測試 task workspace 是否正常",
        "status": "queued",
        "priority": 0,
        "retry_count": 0,
        "max_retries": 0,
        "retry_delay": 0,
        "timeout_ticks": 0,
        "depends_on": [],
        "simulate": "",
        "required_ticks": 1,
        "progress_ticks": 0,
        "history": "queued",
        "workspace_dir": "workspace/tasks",
        "max_replans": 1,
    }

    # 1. 建立 workspace
    task = workspace.create_workspace(task)
    print("workspace created:", task["task_dir"])

    # 2. 建立 plan
    plan = planner.plan(user_input=task["goal"])
    task["steps"] = plan.get("steps", [])
    task["planner_result"] = plan
    workspace.save_plan(task, plan)

    print("plan created:")
    print(plan)

    # 3. 初始化 runtime_state.json
    runtime.ensure_runtime_state(task)

    # 4. 加入 scheduler
    if hasattr(scheduler, "add_task"):
        scheduler.add_task(task)
    elif hasattr(scheduler, "submit_task"):
        scheduler.submit_task(task)
    elif hasattr(scheduler, "enqueue"):
        scheduler.enqueue(task)
    else:
        raise RuntimeError("scheduler 沒有 add_task / submit_task / enqueue 可用方法。")

    # 5. 執行 task
    final_result = None

    for i in range(10):
        if not hasattr(scheduler, "run_next"):
            raise RuntimeError("scheduler 沒有 run_next() 方法。")

        result = scheduler.run_next()
        print(f"tick {i}: {result}")

        task_obj = result.get("task")
        if isinstance(task_obj, dict):
            execution_log = task_obj.get("execution_log", [])
            if execution_log:
                latest_log = execution_log[-1]
                workspace.append_execution_log(task_obj, latest_log)

        status = result.get("status")
        if status in ("completed", "failed", "error"):
            final_result = result
            if isinstance(task_obj, dict):
                workspace.save_result(task_obj, result)
            break

    print("\n=== test finished ===")
    if final_result:
        print(final_result)
    else:
        print("no terminal result within 10 ticks")


if __name__ == "__main__":
    main()