import os
import sys

# 把專案根目錄加入 Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.router import Router
from core.agent_loop import AgentLoop
from core.planner import Planner
from core.task_runtime import TaskRuntime
from core.task_memory import TaskMemory


class AlwaysFailVerifier:
    def verify(self, goal, result):
        return {
            "verified": False,
            "reason": "Forced verifier failure for replan test.",
        }


def run_replan_test():
    print("=== Replan Test Start ===")

    router = Router()
    planner = Planner(llm_client=None)
    task_memory = TaskMemory("workspace")
    verifier = AlwaysFailVerifier()
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
        max_iterations=3,
    )

    result = agent.run("幫我分析這個專案架構")

    print("\n--- Result ---")
    print("Success:", result.get("success"))
    print("Summary:", result.get("summary"))
    print("Error:", result.get("error"))

    data = result.get("data", {})
    if isinstance(data, dict):
        print("Task name:", data.get("task_name"))
        print("Status:", data.get("status"))
        print("Iteration count:", data.get("iteration_count"))
        print("Replanned:", data.get("replanned"))

        history = data.get("replan_history", [])
        print("Replan history count:", len(history))

        for item in history:
            print(
                " - iteration:",
                item.get("iteration"),
                "| reason:",
                item.get("failure_reason"),
            )

        verify_result = data.get("verify_result")
        print("Final verify result:", verify_result)

    print("\n=== Replan Test End ===")


if __name__ == "__main__":
    run_replan_test()