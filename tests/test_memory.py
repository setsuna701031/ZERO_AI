import os
import sys

# 把專案根目錄加入 Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.task_memory import TaskMemory


def run_memory_test():
    print("=== TaskMemory Test Start ===")

    memory = TaskMemory("workspace")

    task_name = "test_memory_case"
    goal = "測試 task memory 是否正常"
    plan = {
        "goal": goal,
        "task_type": "general",
        "steps": [
            {"id": "step_1", "title": "Analyze", "type": "analysis"},
            {"id": "step_2", "title": "Respond", "type": "response"},
        ],
    }

    print("\n--- Create memory ---")
    created = memory.create_task_memory(
        task_name=task_name,
        goal=goal,
        plan=plan,
    )
    print("Created:", isinstance(created, dict))
    print("Initial status:", created.get("status"))

    print("\n--- Update status ---")
    memory.update_status(task_name, "running")
    loaded = memory.load_task_memory(task_name)
    print("Status after update:", loaded.get("status"))

    print("\n--- Add step result ---")
    memory.add_step_result(
        task_name,
        {
            "step": 1,
            "step_text": "Analyze",
            "status": "finished",
            "output": {"note": "step 1 done"},
        },
    )
    loaded = memory.load_task_memory(task_name)
    print("Current step:", loaded.get("current_step"))
    print("Step count:", len(loaded.get("steps", [])))

    print("\n--- Save result ---")
    result = {
        "task_name": task_name,
        "status": "finished",
        "message": "Memory test finished",
    }
    memory.save_result(task_name, result)

    loaded = memory.load_task_memory(task_name)
    print("Final status:", loaded.get("status"))
    print("Result exists:", isinstance(loaded.get("result"), dict))

    print("\n=== TaskMemory Test End ===")


if __name__ == "__main__":
    run_memory_test()