from core.runtime.executor import Executor
from core.runtime.trace_logger import create_trace_logger


def main():
    trace_logger = create_trace_logger(
        task_id="retry_test",
        source="test"
    )

    executor = Executor(
        trace_logger=trace_logger,
        default_retry_limit=1,
    )

    plan = {
        "steps": [
            {
                "type": "write_file",
                "title": "step 1 success",
                "message": "normal success step",
                "status": "done",
            },
            {
                "type": "read_file",
                "title": "step 2 retry then recover",
                "message": "first fail, second pass",
                "retry_limit": 1,
                "fail_until_attempt": 1,
            },
        ]
    }

    print("==== PLAN ====")
    print(plan)

    exec_result = executor.execute_plan(
        task_name="retry_test",
        plan=plan,
        iteration=1
    )

    print("==== EXEC ====")
    print(exec_result)


if __name__ == "__main__":
    main()