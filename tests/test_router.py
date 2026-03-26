import os
import sys

# 把專案根目錄加入 Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.router import Router


def run_router_test():
    print("=== Router Test Start ===")

    router = Router()

    test_inputs = [
        "你好",
        "幫我分析這個專案架構",
        "寫一個python函式",
        "執行 command dir",
        "讀取 workspace 裡的 task_memory.json",
    ]

    for user_input in test_inputs:
        print("\n=== Input ===")
        print(user_input)

        try:
            result = router.route(user_input)
        except Exception as exc:
            result = {"error": str(exc)}

        print("--- Route Result ---")
        print(result)

    print("\n=== Router Test End ===")


if __name__ == "__main__":
    run_router_test()