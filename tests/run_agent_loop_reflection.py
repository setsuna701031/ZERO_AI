import importlib

from core.agent.agent_loop import AgentLoop
from core.planning.planner import Planner
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runtime import TaskRuntime
from core.tasks.task_workspace import TaskWorkspace


def load_scheduler_class():
    module = importlib.import_module("core.tasks.scheduler")

    if hasattr(module, "Scheduler"):
        return getattr(module, "Scheduler")

    if hasattr(module, "TaskScheduler"):
        return getattr(module, "TaskScheduler")

    raise ImportError(
        "core.tasks.scheduler 裡找不到 Scheduler 或 TaskScheduler 類別。"
    )


def build_scheduler(planner, executor, runtime):
    SchedulerClass = load_scheduler_class()

    candidate_kwargs = [
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
    ]

    for kwargs in candidate_kwargs:
        try:
            return SchedulerClass(**kwargs)
        except TypeError:
            continue

    raise RuntimeError("無法建立 scheduler，請檢查 scheduler.__init__ 參數。")


def main():
    planner = Planner()
    step_executor = StepExecutor()
    task_runtime = TaskRuntime()
    task_workspace = TaskWorkspace()

    scheduler = build_scheduler(
        planner=planner,
        executor=step_executor,
        runtime=task_runtime,
    )

    loop = AgentLoop(
        planner=planner,
        step_executor=step_executor,
        scheduler=scheduler,
        task_workspace=task_workspace,
        task_runtime=task_runtime,
        debug=False,
    )

    user_input = "建立任務：幫我做一個測試任務"

    print("=== 1. AgentLoop 建 task ===")
    result = loop.run(user_input)
    print(result)

    print("\n=== 2. 檢查 scheduler queue ===")
    if hasattr(scheduler, "queue"):
        print("queue size:", len(scheduler.queue))
        print("queue:", scheduler.queue)
    else:
        print("scheduler 沒有 queue 屬性")

    print("\n=== 3. 手動跑 scheduler.run_next() ===")
    if hasattr(scheduler, "run_next"):
        run_result = scheduler.run_next()
        print(run_result)
    else:
        print("scheduler 沒有 run_next()")

    print("\n=== 4. 再看 queue ===")
    if hasattr(scheduler, "queue"):
        print("queue size:", len(scheduler.queue))
        print("queue:", scheduler.queue)

    print("\n=== 5. 如果有 task_dir，提示去看資料夾 ===")
    task_dir = result.get("task_dir")
    print("task_dir:", task_dir)


if __name__ == "__main__":
    main()