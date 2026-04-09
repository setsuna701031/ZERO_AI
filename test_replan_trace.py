from core.planning.planner import Planner
from core.runtime.executor import Executor
from core.runtime.trace_logger import create_trace_logger


def main():
    trace_logger = create_trace_logger(
        task_id="replan_test",
        source="test"
    )

    planner = Planner(trace_logger=trace_logger)

    executor = Executor(
        trace_logger=trace_logger,
        planner=planner,
        default_retry_limit=0,   # 不先 retry，直接逼它走 replan
        max_replan_rounds=1,
    )

    # 第一輪故意失敗
    initial_plan = {
        "steps": [
            {
                "type": "read_file",
                "title": "step 1 force fail",
                "message": "force failure to trigger replan",
                "force_error": True,
                "retry_limit": 0,
            }
        ]
    }

    print("==== INITIAL PLAN ====")
    print(initial_plan)

    result = executor.execute_plan(
        task_name="replan_test",
        plan=initial_plan,
        iteration=1,
    )

    print("==== FINAL RESULT ====")
    print(result)


if __name__ == "__main__":
    main()