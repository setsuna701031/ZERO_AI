from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.runtime.step_executor import StepExecutor


def print_block(title: str, data) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    if isinstance(data, dict):
        pprint(data, sort_dicts=False)
    else:
        print(data)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    executor = StepExecutor(debug=True)

    print("\n[StepExecutor Smoke Test]")
    print(f"project_root = {PROJECT_ROOT}")

    # 1. list handlers
    handlers = executor.list_handlers()
    print_block("1. list_handlers", handlers)

    assert_true(isinstance(handlers, list), "handlers should be a list")
    assert_true("write_file" in handlers, "write_file handler should exist")
    assert_true("read_file" in handlers, "read_file handler should exist")
    assert_true("command" in handlers, "command handler should exist")
    assert_true("verify" in handlers, "verify handler should exist")

    # 2. unsupported step type
    result_unsupported = executor.execute_step({"type": "not_real_step"})
    print_block("2. unsupported step type", result_unsupported)

    assert_true(result_unsupported["ok"] is False, "unsupported step should fail")
    assert_true(result_unsupported["error"] is not None, "unsupported step should have error")
    assert_true(
        result_unsupported["error"]["type"] == "unsupported_step_type",
        "unsupported step error type mismatch",
    )

    # 3. execute_steps with one failing step
    result_batch_fail = executor.execute_steps(
        steps=[
            {"type": "not_real_step"},
            {"type": "not_real_step_again"},
        ],
        task=None,
        context=None,
    )
    print_block("3. execute_steps fail", result_batch_fail)

    assert_true(result_batch_fail["ok"] is False, "batch with invalid step should fail")
    assert_true(result_batch_fail["failed_step"] == 0, "failed_step should be 0")
    assert_true(result_batch_fail["step_count"] == 2, "step_count should be 2")
    assert_true(result_batch_fail["completed_steps"] == 0, "completed_steps should be 0")
    assert_true(isinstance(result_batch_fail["results"], list), "results should be list")
    assert_true(len(result_batch_fail["results"]) == 1, "batch should stop at first failed step")

    # 4. execute_steps with empty steps
    result_batch_empty = executor.execute_steps(
        steps=[],
        task=None,
        context=None,
    )
    print_block("4. execute_steps empty", result_batch_empty)

    assert_true(result_batch_empty["ok"] is True, "empty batch should succeed")
    assert_true(result_batch_empty["step_count"] == 0, "empty batch step_count should be 0")
    assert_true(result_batch_empty["completed_steps"] == 0, "empty batch completed_steps should be 0")
    assert_true(result_batch_empty["failed_step"] is None, "empty batch failed_step should be None")
    assert_true(result_batch_empty["error"] is None, "empty batch error should be None")

    print("\n" + "=" * 80)
    print("驗收結論")
    print("=" * 80)
    print("1. StepExecutor 可正常建立")
    print("2. unsupported step type 會回固定錯誤格式")
    print("3. execute_steps 失敗批次格式固定")
    print("4. execute_steps 空批次格式固定")
    print("\nPASS: test_step_executor.py")


if __name__ == "__main__":
    main()