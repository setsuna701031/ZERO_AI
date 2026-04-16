from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.runtime.executor import Executor
from core.runtime.trace_logger import create_trace_logger
from core.planning.planner import Planner


def print_block(title: str, data) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    if isinstance(data, dict):
        pprint(data, sort_dicts=False)
    else:
        print(data)


def main() -> None:
    print("\n[Executor Repair Rules Test]")
    print(f"project_root = {PROJECT_ROOT}")

    trace_logger = create_trace_logger(
        task_id="repair_rules_test",
        source="test",
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
                "type": "read_file",
                "path": "nested/demo/hello.txt",
                "title": "read nested file",
                "message": "should trigger mkdir + write repair",
                "status": "done",
            }
        ]
    }

    print_block("INITIAL PLAN", initial_plan)

    result = executor.execute_plan(
        task_name="repair_rules_test",
        plan=initial_plan,
        iteration=1,
    )

    print_block("FINAL RESULT", result)


if __name__ == "__main__":
    main()