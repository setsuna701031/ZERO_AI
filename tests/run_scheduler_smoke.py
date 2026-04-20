from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.tasks.scheduler import Scheduler


def print_block(title: str, data: Any) -> None:
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


def build_scheduler() -> Scheduler:
    scheduler = Scheduler(
        workspace_dir="workspace",
        allow_commands=True,
        debug=True,
    )
    scheduler.agent_loop = None
    scheduler._agent_loop = None
    scheduler.task_manager = None
    return scheduler


def extract_task_id(create_result: Dict[str, Any]) -> str:
    for key in ("task_id", "id"):
        value = str(create_result.get(key) or "").strip()
        if value:
            return value

    task = create_result.get("task")
    if isinstance(task, dict):
        for key in ("task_id", "id", "task_name"):
            value = str(task.get(key) or "").strip()
            if value:
                return value

    raise AssertionError("create_task did not return task_id")


def main() -> None:
    print("\n[Scheduler Smoke Test]")
    print(f"project_root = {PROJECT_ROOT}")

    scheduler = build_scheduler()
    workspace_root = Path("workspace").resolve()
    shared_dir = workspace_root / "shared"

    # 1. create minimal inline task
    # 這裡要直接進 queued，不能停在 created，不然 tick 不一定會跑到它
    create_result = scheduler._create_task_record(
        goal=(
            "建立 smoke task "
            ":: step=write_file:shared/scheduler_smoke.txt|hello scheduler "
            ":: step=verify:contains=hello"
        ),
        priority=0,
        initial_status="queued",
    )
    print_block("1. create task", create_result)

    assert_true(create_result["ok"] is True, "create task should succeed")
    task_id = extract_task_id(create_result)

    task = scheduler._get_task_from_repo(task_id)
    print_block("1b. created task from repo", task)

    assert_true(isinstance(task, dict), "created task should exist in repo")
    assert_true(
        str(task.get("status") or "").strip().lower() in {"queued", "ready", "retry"},
        "created task should be ready for scheduler dispatch",
    )
    assert_true(isinstance(task.get("steps"), list), "task steps should be list")
    assert_true(len(task.get("steps", [])) >= 2, "task should contain parsed steps")

    # 2. queue rows / snapshot structure
    queue_rows = scheduler.get_queue_rows()
    print_block("2. queue rows", queue_rows)

    assert_true(queue_rows["ok"] is True, "get_queue_rows should succeed")
    assert_true("rows" in queue_rows, "queue rows should contain rows")

    snapshot_before = scheduler.get_queue_snapshot()
    print_block("2b. queue snapshot before tick", snapshot_before)

    assert_true(snapshot_before["ok"] is True, "get_queue_snapshot should succeed")
    assert_true("ready_queue" in snapshot_before, "snapshot should contain ready_queue")
    assert_true("running_tasks" in snapshot_before, "snapshot should contain running_tasks")

    # 3. tick until task finished
    tick_results = []
    for i in range(10):
        tick_result = scheduler.tick()
        tick_results.append(tick_result)
        print_block(f"3.{i} tick result", tick_result)

        task = scheduler._get_task_from_repo(task_id)
        if isinstance(task, dict):
            status = str(task.get("status") or "").strip().lower()
            if status in {"finished", "done", "success", "completed"}:
                break

    task = scheduler._get_task_from_repo(task_id)
    print_block("3.final task", task)

    assert_true(isinstance(task, dict), "task should still exist after ticks")
    final_status = str(task.get("status") or "").strip().lower()
    assert_true(
        final_status in {"finished", "done", "success", "completed"},
        "task should finish after ticks",
    )
    final_answer = str(task.get("final_answer") or "")
    assert_true(final_answer != "", "finished task should have final_answer")

    expected_file = shared_dir / "scheduler_smoke.txt"
    assert_true(expected_file.exists(), "scheduler smoke file should exist in shared dir")
    assert_true(
        expected_file.read_text(encoding="utf-8") == "hello scheduler",
        "scheduler smoke file content mismatch",
    )

    # 4. finished task should not re-run destructively
    tick_after_finished = scheduler.tick()
    print_block("4. tick after finished", tick_after_finished)

    task_after_finished = scheduler._get_task_from_repo(task_id)
    print_block("4b. finished task after extra tick", task_after_finished)

    assert_true(isinstance(task_after_finished, dict), "finished task should still exist")
    assert_true(
        str(task_after_finished.get("status") or "").strip().lower()
        in {"finished", "done", "success", "completed"},
        "finished task should remain terminal after extra tick",
    )

    # 5. blocked / invalid dependency create should be rejected
    blocked_create = scheduler._create_task_record(
        goal="blocked dependency smoke :: step=write_file:shared/blocked_should_not_write.txt|blocked",
        depends_on=["task_not_exists_123456"],
        priority=0,
        initial_status="queued",
    )
    print_block("5. create blocked task", blocked_create)

    assert_true(blocked_create["ok"] is False, "blocked task with missing dependency should fail create")

    # 6. snapshot after work
    snapshot_after = scheduler.get_queue_snapshot()
    print_block("6. queue snapshot after work", snapshot_after)

    assert_true(snapshot_after["ok"] is True, "snapshot after work should succeed")
    assert_true("task_count" in snapshot_after, "snapshot after work should contain task_count")

    print("\n" + "=" * 80)
    print("驗收結論")
    print("=" * 80)
    print("1. create_task 基本流程可用")
    print("2. queue rows / snapshot 結構可用")
    print("3. minimal inline task 可從 queued 經 tick 跑到 finished")
    print("4. finished task 不會因額外 tick 變回非 terminal")
    print("5. 缺失 dependency 的 blocked task 會被擋住")
    print("\nPASS: test_scheduler_smoke.py")


if __name__ == "__main__":
    main()