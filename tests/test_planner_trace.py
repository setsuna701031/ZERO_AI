from core.planning.planner import Planner
from core.runtime.executor import Executor
from core.runtime.trace_logger import create_trace_logger


def main():
    # 建立 trace logger（共享給 planner + executor）
    trace_logger = create_trace_logger(
        task_id="planner_test",
        source="test"
    )

    # 建 planner + executor（都接同一個 logger）
    planner = Planner(trace_logger=trace_logger)
    executor = Executor(trace_logger=trace_logger)

    # 模擬使用者輸入
    user_input = "建立 hello.txt 然後讀取 hello.txt"

    # 1️⃣ planner
    plan_result = planner.plan(user_input=user_input)

    print("==== PLAN ====")
    print(plan_result)

    # 2️⃣ executor
    exec_result = executor.execute_plan(
        task_name="planner_test",
        plan=plan_result,
        iteration=1
    )

    print("==== EXEC ====")
    print(exec_result)


if __name__ == "__main__":
    main()