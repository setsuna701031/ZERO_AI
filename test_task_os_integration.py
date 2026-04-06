from __future__ import annotations

import json
import os
import shutil
from typing import Any, Dict, List

from services.system_boot import ZeroSystem


WORKSPACE = "workspace"


def print_title(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def safe_read_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def reset_workspace() -> None:
    if os.path.exists(WORKSPACE):
        shutil.rmtree(WORKSPACE)
    os.makedirs(WORKSPACE, exist_ok=True)


def print_repo_tasks(system: ZeroSystem, title: str) -> None:
    print_title(title)
    result = system.list_tasks()
    tasks = result.get("tasks", []) if isinstance(result, dict) else []

    if not tasks:
        print("(no tasks)")
        return

    for task in tasks:
        print(
            f"task_id={task.get('task_id')}, "
            f"status={task.get('status')}, "
            f"depends_on={task.get('depends_on')}, "
            f"current_step_index={task.get('current_step_index')}, "
            f"steps_total={task.get('steps_total')}, "
            f"final_answer={repr(task.get('final_answer'))}"
        )


def print_tick_result(tick_result: Dict[str, Any], title: str) -> None:
    print_title(title)
    print(json.dumps(tick_result, ensure_ascii=False, indent=2))


def print_runtime_state(task_id: str, title: str) -> None:
    runtime_path = os.path.join(WORKSPACE, "tasks", task_id, "runtime_state.json")
    print_title(title)
    print(f"runtime_state_file = {runtime_path}")

    data = safe_read_json(runtime_path)
    if data is None:
        print("(runtime_state.json not found)")
        return

    print(
        json.dumps(
            {
                "task_name": data.get("task_name"),
                "status": data.get("status"),
                "depends_on": data.get("depends_on"),
                "current_step_index": data.get("current_step_index"),
                "steps_total": data.get("steps_total"),
                "retry_count": data.get("retry_count"),
                "replan_count": data.get("replan_count"),
                "blocked_reason": data.get("blocked_reason"),
                "failure_type": data.get("failure_type"),
                "failure_message": data.get("failure_message"),
                "final_answer": data.get("final_answer"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def print_queue_snapshot(system: ZeroSystem, title: str) -> None:
    print_title(title)
    snapshot = system.get_queue_snapshot()
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


def submit_demo_tasks(system: ZeroSystem) -> Dict[str, str]:
    """
    建兩個任務：
    1. task_a：先寫檔，再讀檔
    2. task_b：依賴 task_a，內容為 noop
    """

    result_a = system.submit_task(
        goal=(
            "demo task a"
            "::step=write_file:hello.txt|hello from task_a"
            "::step=read_file:hello.txt"
        ),
        priority=10,
    )

    if not result_a.get("ok"):
        raise RuntimeError(f"submit task_a failed: {result_a}")

    task_a = result_a["task"]["task_id"]

    result_b = system.submit_task(
        goal=(
            "demo task b"
            f"::depends_on={task_a}"
            "::step=noop"
        ),
        priority=5,
    )

    if not result_b.get("ok"):
        raise RuntimeError(f"submit task_b failed: {result_b}")

    task_b = result_b["task"]["task_id"]

    return {
        "task_a": task_a,
        "task_b": task_b,
    }


def assert_status(system: ZeroSystem, task_id: str, expected: str) -> None:
    result = system.get_task(task_id)
    if not result.get("ok"):
        raise AssertionError(f"task not found: {task_id}")

    actual = str(result["task"].get("status") or "").strip().lower()
    if actual != expected:
        raise AssertionError(
            f"status mismatch for {task_id}: expected={expected}, actual={actual}"
        )


def run_main_flow_test() -> None:
    reset_workspace()

    system = ZeroSystem(workspace=WORKSPACE)

    print_title("SYSTEM HEALTH")
    print(json.dumps(system.health(), ensure_ascii=False, indent=2))

    ids = submit_demo_tasks(system)
    task_a = ids["task_a"]
    task_b = ids["task_b"]

    print_repo_tasks(system, "提交任務後的 repo 狀態（預期 task_a queued, task_b blocked）")
    print_queue_snapshot(system, "提交任務後 queue snapshot")

    # 初始狀態檢查
    assert_status(system, task_a, "queued")
    assert_status(system, task_b, "blocked")

    # Tick #1
    tick_1 = system.tick()
    print_tick_result(tick_1, "TICK #1")
    print_repo_tasks(system, "TICK #1 後 repo 狀態")
    print_runtime_state(task_a, "task_a runtime_state after tick #1")
    print_runtime_state(task_b, "task_b runtime_state after tick #1")
    print_queue_snapshot(system, "TICK #1 後 queue snapshot")

    # task_a 應該已被跑過；task_b 還可能 blocked/queued，視 scheduler 實作
    task_a_info = system.get_task(task_a)
    if not task_a_info.get("ok"):
        raise AssertionError("task_a missing after tick #1")

    task_a_status = str(task_a_info["task"].get("status") or "").strip().lower()
    if task_a_status not in {"queued", "finished"}:
        raise AssertionError(f"unexpected task_a status after tick #1: {task_a_status}")

    # Tick #2
    tick_2 = system.tick()
    print_tick_result(tick_2, "TICK #2")
    print_repo_tasks(system, "TICK #2 後 repo 狀態")
    print_runtime_state(task_a, "task_a runtime_state after tick #2")
    print_runtime_state(task_b, "task_b runtime_state after tick #2")
    print_queue_snapshot(system, "TICK #2 後 queue snapshot")

    # 這時 task_a 應該 finished，task_b 應該至少被解鎖成 queued 或已完成
    task_a_info = system.get_task(task_a)
    task_b_info = system.get_task(task_b)

    if not task_a_info.get("ok"):
        raise AssertionError("task_a missing after tick #2")
    if not task_b_info.get("ok"):
        raise AssertionError("task_b missing after tick #2")

    task_a_status = str(task_a_info["task"].get("status") or "").strip().lower()
    task_b_status = str(task_b_info["task"].get("status") or "").strip().lower()

    if task_a_status != "finished":
        raise AssertionError(f"task_a should be finished after tick #2, got: {task_a_status}")

    if task_b_status not in {"queued", "finished"}:
        raise AssertionError(
            f"task_b should be queued or finished after tick #2, got: {task_b_status}"
        )

    # Tick #3
    tick_3 = system.tick()
    print_tick_result(tick_3, "TICK #3")
    print_repo_tasks(system, "TICK #3 後 repo 狀態")
    print_runtime_state(task_a, "task_a runtime_state after tick #3")
    print_runtime_state(task_b, "task_b runtime_state after tick #3")
    print_queue_snapshot(system, "TICK #3 後 queue snapshot")

    # 最終預期：兩個都 finished
    assert_status(system, task_a, "finished")
    assert_status(system, task_b, "finished")

    # 額外看 task_a 的 runtime 最後答案
    runtime_a = safe_read_json(os.path.join(WORKSPACE, "tasks", task_a, "runtime_state.json"))
    runtime_b = safe_read_json(os.path.join(WORKSPACE, "tasks", task_b, "runtime_state.json"))

    print_title("FINAL ASSERTIONS")
    print("task_a final status = finished")
    print("task_b final status = finished")

    if isinstance(runtime_a, dict):
        print(f"task_a final_answer = {repr(runtime_a.get('final_answer'))}")
    if isinstance(runtime_b, dict):
        print(f"task_b final_answer = {repr(runtime_b.get('final_answer'))}")

    print("\nALL INTEGRATION TESTS PASSED")


if __name__ == "__main__":
    run_main_flow_test()