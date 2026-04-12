from core.runtime.executor import Executor
from core.runtime.trace_logger import create_trace_logger
from core.planning.planner import Planner


def main():
    trace_logger = create_trace_logger(
        task_id="safe_path_repair_test",
        source="test"
    )

    planner = Planner(trace_logger=trace_logger)

    executor = Executor(
        trace_logger=trace_logger,
        planner=planner,
        default_retry_limit=0,
        max_replan_rounds=1,
        enable_forced_repair=True,
    )

    initial_plan = {
        "steps": [
            {
                "type": "write_file",
                "path": "blocked/output.txt",
                "title": "write blocked path",
                "message": "should trigger safe path fallback",
                "simulate_write_failure": True,
                "status": "done",
            }
        ]
    }

    print("==== INITIAL PLAN ====")
    print(initial_plan)

    result = executor.execute_plan(
        task_name="safe_path_repair_test",
        plan=initial_plan,
        iteration=1,
    )

    print("==== FINAL RESULT ====")
    print(result)


if __name__ == "__main__":
    main()