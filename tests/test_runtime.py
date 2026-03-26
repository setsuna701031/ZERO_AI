import os
import sys
import time

# 把專案根目錄加入 Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.planner import Planner
from core.task_runtime import TaskRuntime


def build_task_name(goal: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in goal.lower()).strip("_")
    if not safe:
        safe = "task"
    safe = safe[:30]
    return f"test_{safe}_{int(time.time())}"


def run_runtime_test():
    print("=== Runtime Test Start ===")

    planner = Planner(llm_client=None)
    runtime = TaskRuntime(
        workspace_root="workspace",
        task_manager=None,
        tool_registry=None,
        llm_client=None,
    )

    test_goals = [
        "幫我分析這個專案",
        "寫一個python函式",
    ]

    for goal in test_goals:
        print("\n=== Goal ===")
        print(goal)

        plan = planner.create_plan(goal=goal)

        task_info = {
            "task_name": build_task_name(goal),
            "goal": goal,
            "task_kind": "general",
            "metadata": {},
        }

        result = runtime.run_task(task_info, plan)

        print("\n--- Result ---")
        print("Success:", result.get("success"))
        print("Summary:", result.get("summary"))

        data = result.get("data", {})
        if isinstance(data, dict):
            print("Task name:", data.get("task_name"))
            print("Task dir:", data.get("task_dir"))
            print("Plan file:", data.get("plan_file"))
            print("Result file:", data.get("result_file"))
            print("Step count:", data.get("step_count"))

    print("\n=== Runtime Test End ===")


if __name__ == "__main__":
    run_runtime_test()