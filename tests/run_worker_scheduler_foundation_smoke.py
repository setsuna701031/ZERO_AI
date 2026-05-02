from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.worker import (
    WorkerRuntime,
    WorkerScheduler,
    ensure_scheduler_state_contract,
    ensure_worker_state_snapshot_contract,
)


PREFIX = "[worker-scheduler-foundation-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    calls = []
    attempts_by_task = {}

    def fake_zero_runner(worker_task):
        task_id = worker_task["task_id"]
        calls.append(task_id)
        attempts_by_task[task_id] = attempts_by_task.get(task_id, 0) + 1

        if task_id == "worker_retry_once" and attempts_by_task[task_id] == 1:
            return {
                "ok": False,
                "status": "failed",
                "summary": "transient deterministic failure",
                "result": {"attempt": attempts_by_task[task_id]},
                "trace": [{"event_type": "worker_failed_once", "task_id": task_id}],
                "confidence": 0.0,
            }

        return {
            "ok": True,
            "status": "success",
            "summary": f"done {task_id}",
            "result": {"attempt": attempts_by_task[task_id]},
            "artifacts": [{"kind": "text", "path": f"workspace/worker/{task_id}.txt"}],
            "trace": [{"event_type": "worker_done", "task_id": task_id}],
            "confidence": 0.9,
        }

    runtime = WorkerRuntime(runner=fake_zero_runner)
    task_a = runtime.create_task(
        task_id="worker_first",
        parent_task_id="parent_scheduler",
        role="first",
        objective="run first",
        input_context={},
    )
    task_b = runtime.create_task(
        task_id="worker_retry_once",
        parent_task_id="parent_scheduler",
        role="retry",
        objective="run with one retry",
        input_context={},
    )

    scheduler = WorkerScheduler(runtime=runtime, max_retries=1)
    scheduler.enqueue(task_a)
    scheduler.enqueue(task_b)
    initial_state = scheduler.snapshot_state()
    try:
        ensure_scheduler_state_contract(initial_state)
    except Exception as exc:
        return fail(f"initial scheduler state contract failed: {exc}\n{initial_state}")
    if [item["status"] for item in initial_state["queue"]] != ["pending", "pending"]:
        return fail(f"queue should start as pending: {initial_state}")
    pass_step("queue tracks pending worker tasks")

    first_event = scheduler.run_next()
    if first_event.get("event") != "done" or first_event.get("task_id") != "worker_first":
        return fail(f"first scheduler tick should finish first worker: {first_event}")
    if calls != ["worker_first"]:
        return fail(f"scheduler should run only one worker per tick: {calls}")
    pass_step("scheduler runs worker_task in order, one per tick")

    retry_event = scheduler.run_next()
    if retry_event.get("event") != "retry" or retry_event.get("task_id") != "worker_retry_once":
        return fail(f"second scheduler tick should schedule retry: {retry_event}")
    retry_state = retry_event.get("state")
    if not isinstance(retry_state, dict) or retry_state["queue"][0]["status"] != "pending":
        return fail(f"retry should return task to pending queue: {retry_event}")
    pass_step("basic retry requeues failed worker_task deterministically")

    done_retry_event = scheduler.run_next()
    if done_retry_event.get("event") != "done" or done_retry_event.get("task_id") != "worker_retry_once":
        return fail(f"third scheduler tick should finish retried worker: {done_retry_event}")
    if calls != ["worker_first", "worker_retry_once", "worker_retry_once"]:
        return fail(f"scheduler call order changed or became parallel: {calls}")
    pass_step("retry success updates done state")

    final_state = scheduler.snapshot_state()
    try:
        ensure_scheduler_state_contract(final_state)
    except Exception as exc:
        return fail(f"final scheduler state contract failed: {exc}\n{final_state}")
    if final_state["queue"]:
        return fail(f"queue should be empty after all work is done: {final_state}")
    if len(final_state["done"]) != 2 or final_state["failed"]:
        return fail(f"scheduler should have two done and no failed items: {final_state}")
    if final_state["tick_count"] != 3:
        return fail(f"scheduler tick_count should count three run_next calls: {final_state}")
    pass_step("scheduler state updates queue, done, failed, and tick_count")

    worker_state = runtime.snapshot_state()
    try:
        ensure_worker_state_snapshot_contract(worker_state)
    except Exception as exc:
        return fail(f"worker state snapshot contract failed: {exc}\n{worker_state}")
    if len(worker_state.get("completed_tasks", [])) != 2:
        return fail(f"worker runtime should have two completed results: {worker_state}")
    pass_step("scheduler updates worker_runtime state")

    fail_runtime = WorkerRuntime(
        runner=lambda worker_task: {
            "ok": False,
            "status": "failed",
            "summary": "always failed",
            "result": {},
            "trace": [{"event_type": "worker_failed", "task_id": worker_task["task_id"]}],
            "confidence": 0.0,
        }
    )
    fail_task = fail_runtime.create_task(
        task_id="worker_always_failed",
        parent_task_id="parent_scheduler",
        role="failed",
        objective="fail closed",
        input_context={},
    )
    fail_scheduler = WorkerScheduler(runtime=fail_runtime, max_retries=0)
    fail_scheduler.enqueue(fail_task)
    failed_event = fail_scheduler.run_next()
    if failed_event.get("event") != "failed":
        return fail(f"scheduler should move exhausted task to failed: {failed_event}")
    failed_state = fail_scheduler.snapshot_state()
    if len(failed_state["failed"]) != 1 or failed_state["queue"]:
        return fail(f"failed task should leave queue and enter failed: {failed_state}")
    pass_step("exhausted retry moves worker_task to failed")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
