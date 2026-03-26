import sys
import os

# 把專案根目錄加入 Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.planner import Planner


def run_planner_test():
    print("=== Planner Test Start ===")

    planner = Planner(llm_client=None)

    test_goals = [
        "幫我分析這個專案結構",
        "寫一個python函式計算費氏數列",
        "讀取workspace裡面的task_memory.json",
        "執行 command dir",
    ]

    for goal in test_goals:
        print("\n--- Goal ---")
        print(goal)

        plan = planner.create_plan(goal=goal)

        print("Plan OK:", isinstance(plan, dict))

        steps = plan.get("steps")
        print("Steps exist:", isinstance(steps, list))

        if isinstance(steps, list):
            print("Step count:", len(steps))
            for step in steps:
                print(" -", step.get("title"), "|", step.get("type"))

    print("\n=== Planner Test End ===")


if __name__ == "__main__":
    run_planner_test()