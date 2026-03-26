import os
import sys

# 把專案根目錄加入 Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.verifier import Verifier


def run_verifier_test():
    print("=== Verifier Test Start ===")

    verifier = Verifier(llm_client=None)

    goal = "寫一個python函式"

    fake_task_result = {
        "task_name": "test_task",
        "goal": goal,
        "steps": [
            {"step": 1, "status": "finished"},
            {"step": 2, "status": "finished"},
        ],
        "result": {
            "status": "success",
            "message": "Task finished successfully.",
        },
    }

    verify_result = verifier.verify(
        goal=goal,
        result=fake_task_result,
    )

    print("\n--- Verify Result ---")
    print("Verified:", verify_result.get("verified"))
    print("Reason:", verify_result.get("reason"))

    print("\n=== Verifier Test End ===")


if __name__ == "__main__":
    run_verifier_test()