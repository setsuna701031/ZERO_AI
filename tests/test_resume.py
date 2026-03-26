import os
import sys

# 把專案根目錄加入 Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.router import Router
from core.agent_loop import AgentLoop
from core.planner import Planner
from core.task_runtime import TaskRuntime
from core.verifier import Verifier
from core.task_memory import TaskMemory


def run_resume_test():
    print("=== Resume Test Start ===")

    router = Router()
    planner = Planner(llm_client=None)
    task_memory = TaskMemory("workspace")
    verifier = Verifier(llm_client=None)
    task_runtime = TaskRuntime(
        workspace_root="workspace",
        task_manager=None,
        tool_registry=None,
        llm_client=None,
        task_memory=task_memory,
    )

    agent = AgentLoop(
        router=router,
        planner=planner,
        task_runtime=task_runtime,
        verifier=verifier,
        llm_client=None,
        task_memory=task_memory,
    )

    print("\n--- Step 1: create unfinished task ---")
    task_name = "test_resume_case"
    goal = "寫一個python函式"

    plan = planner.create_plan(goal=goal)
    task_memory.create_task_memory(
        task_name=task_name,
        goal=goal,
        plan=plan,
    )
    task_memory.update_status(task_name, "running")
    task_memory.update_current_step(task_name, 1)

    print("Created unfinished task:", task_name)
    print("Current unfinished task:", task_memory.get_last_unfinished_task())

    print("\n--- Step 2: resume ---")
    result = agent.run("繼續任務")

    print("Success:", result.get("success"))
    print("Summary:", result.get("summary"))
    print("Error:", result.get("error"))

    data = result.get("data", {})
    if isinstance(data, dict):
        print("Task name:", data.get("task_name"))
        print("Status:", data.get("status"))
        print("Task dir:", data.get("task_dir"))
        print("Step count:", data.get("step_count"))

    print("\n=== Resume Test End ===")


if __name__ == "__main__":
    run_resume_test()