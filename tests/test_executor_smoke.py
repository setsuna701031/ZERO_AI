from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.runtime.executor import Executor


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


def build_executor() -> Executor:
    return Executor(
        workspace_root="workspace",
        default_retry_limit=0,
        max_replan_rounds=0,
        enable_forced_repair=True,
    )


def main() -> None:
    print("\n[Executor Smoke Test]")
    print(f"project_root = {PROJECT_ROOT}")

    executor = build_executor()
    workspace_root = Path("workspace").resolve()

    # 1. empty plan
    result_empty = executor.execute_plan(
        task_name="executor_smoke_empty",
        plan={"steps": []},
        iteration=1,
    )
    print_block("1. empty plan", result_empty)

    assert_true(result_empty["success"] is False, "empty plan should not be treated as success")
    assert_true(result_empty["needs_correction"] is True, "empty plan should need correction")
    assert_true(len(result_empty["rounds"]) == 1, "empty plan should still produce one round")

    # 2. simple write_file success
    write_task = "executor_smoke_write"
    write_result = executor.execute_plan(
        task_name=write_task,
        plan={
            "steps": [
                {
                    "type": "write_file",
                    "path": "hello.txt",
                    "content": "executor hello",
                    "title": "write hello.txt",
                    "status": "done",
                }
            ]
        },
        iteration=1,
    )
    print_block("2. write_file success", write_result)

    assert_true(write_result["success"] is True, "write_file plan should succeed")
    written_file = workspace_root / write_task / "hello.txt"
    assert_true(written_file.exists(), "written file should exist")
    assert_true(written_file.read_text(encoding="utf-8") == "executor hello", "written content mismatch")

    # 3. read_file success
    read_task = "executor_smoke_read"
    read_dir = workspace_root / read_task
    read_dir.mkdir(parents=True, exist_ok=True)
    (read_dir / "input.txt").write_text("read me", encoding="utf-8")

    read_result = executor.execute_plan(
        task_name=read_task,
        plan={
            "steps": [
                {
                    "type": "read_file",
                    "path": "input.txt",
                    "title": "read input.txt",
                    "status": "done",
                }
            ]
        },
        iteration=1,
    )
    print_block("3. read_file success", read_result)

    assert_true(read_result["success"] is True, "read_file plan should succeed")
    round_results = read_result["final_round_result"]["results"]
    assert_true(len(round_results) == 1, "read_file should produce one step result")
    assert_true(round_results[0]["output"] == "read me", "read output mismatch")

    # 4. retry exhausted (use mkdir + force_error, avoid repair paths)
    retry_task = "executor_smoke_retry"
    retry_result = executor.execute_plan(
        task_name=retry_task,
        plan={
            "steps": [
                {
                    "type": "mkdir",
                    "path": "will_fail_dir",
                    "title": "force fail mkdir",
                    "status": "done",
                    "force_error": True,
                }
            ]
        },
        iteration=1,
    )
    print_block("4. retry exhausted", retry_result)

    assert_true(retry_result["success"] is False, "forced mkdir error plan should fail")
    retry_round_results = retry_result["final_round_result"]["results"]
    assert_true(len(retry_round_results) == 1, "retry fail should still have one step result")
    retry_info = retry_round_results[0].get("retry_info", {})
    assert_true(retry_info.get("attempts") == 1, "retry attempts should be 1 when retry_limit=0")
    assert_true(retry_info.get("recovered") is False, "retry exhausted should not be recovered")
    assert_true(
        retry_round_results[0].get("status") == "error",
        "forced mkdir should end with error status",
    )

    # 5. safe path fallback
    safe_task = "executor_smoke_safe_path"
    safe_result = executor.execute_plan(
        task_name=safe_task,
        plan={
            "steps": [
                {
                    "type": "write_file",
                    "path": "blocked/output.txt",
                    "content": "safe fallback content",
                    "title": "simulate blocked write",
                    "status": "done",
                    "simulate_write_failure": True,
                }
            ]
        },
        iteration=1,
    )
    print_block("5. safe path fallback", safe_result)

    assert_true(safe_result["success"] is True, "safe path fallback plan should succeed")
    safe_round_results = safe_result["final_round_result"]["results"]
    assert_true(len(safe_round_results) >= 1, "safe path fallback should produce at least one step result")

    repaired_candidates = [
        item for item in safe_round_results
        if item.get("repair_type") == "safe_path_fallback"
    ]
    assert_true(len(repaired_candidates) == 1, "should have exactly one safe_path_fallback repaired result")

    repaired_result = repaired_candidates[0]
    repaired_path = repaired_result.get("resolved_path", "")
    assert_true("_repaired" in repaired_path, "resolved_path should point to _repaired fallback location")
    assert_true(
        repaired_result.get("repaired_from_path") == "blocked/output.txt",
        "repaired_from_path should match original blocked path",
    )

    print("\n" + "=" * 80)
    print("驗收結論")
    print("=" * 80)
    print("1. execute_plan 空 plan 行為固定")
    print("2. write_file 成功路徑固定")
    print("3. read_file 成功路徑固定")
    print("4. retry exhausted 結構固定")
    print("5. safe path fallback 結構固定")
    print("\nPASS: test_executor_smoke.py")


if __name__ == "__main__":
    main()