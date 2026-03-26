import os
import sys

# 把專案根目錄加入 Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.router import Router
from core.agent_loop import AgentLoop
from core.planner import Planner
from core.task_runtime import TaskRuntime
from core.verifier import Verifier


def run_agent_loop_test():
    print("=== AgentLoop Test Start ===")

    router = Router()
    planner = Planner(llm_client=None)
    verifier = Verifier(llm_client=None)
    task_runtime = TaskRuntime(
        workspace_root="workspace",
        task_manager=None,
        tool_registry=None,
        llm_client=None,
    )

    agent = AgentLoop(
        router=router,
        planner=planner,
        task_runtime=task_runtime,
        verifier=verifier,
        llm_client=None,
    )

    test_inputs = [
        "你好",
        "幫我分析這個專案架構",
        "寫一個python函式",
    ]

    for user_input in test_inputs:
        print("\n=== Input ===")
        print(user_input)

        result = agent.run(user_input)

        print("\n--- Agent Result ---")
        print("Success:", result.get("success"))
        print("Summary:", result.get("summary"))
        print("Error:", result.get("error"))

        data = result.get("data", {})
        if isinstance(data, dict):
            if "response" in data:
                print("Response:", data.get("response"))
            if "task_name" in data:
                print("Task name:", data.get("task_name"))
            if "status" in data:
                print("Status:", data.get("status"))

    print("\n=== AgentLoop Test End ===")


if __name__ == "__main__":
    run_agent_loop_test()