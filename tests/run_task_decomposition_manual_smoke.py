from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.worker import (
    WorkerRuntime,
    create_manual_parent_task,
    ensure_parent_task_contract,
    ensure_worker_state_snapshot_contract,
    ensure_worker_task_contract,
    run_manual_decomposition,
)


PREFIX = "[task-decomposition-manual-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    delegated_order = []

    def fake_zero_runner(worker_task):
        delegated_order.append(worker_task["task_id"])
        return {
            "ok": True,
            "status": "success",
            "summary": f"manual worker completed: {worker_task['task_id']}",
            "result": {
                "parent_task_id": worker_task["parent_task_id"],
                "objective": worker_task["objective"],
            },
            "artifacts": [
                {
                    "kind": "manual_worker_output",
                    "path": f"workspace/worker/{worker_task['task_id']}.json",
                }
            ],
            "trace": [
                {
                    "event_type": "manual_worker_run",
                    "task_id": worker_task["task_id"],
                }
            ],
            "confidence": 0.95,
        }

    parent_task = create_manual_parent_task(
        task_id="parent_manual_report",
        objective="prepare a tiny manual report",
        input_context={
            "source": "manual smoke input",
        },
    )
    try:
        ensure_parent_task_contract(parent_task)
    except Exception as exc:
        return fail(f"parent_task contract failed: {exc}\n{parent_task}")
    if parent_task.get("decomposition_mode") != "manual":
        return fail(f"parent_task should be manual-only: {parent_task}")
    pass_step("can define one manual parent task")

    runtime = WorkerRuntime(runner=fake_zero_runner)
    result = run_manual_decomposition(
        parent_task=parent_task,
        worker_specs=[
            {
                "task_id": "manual_worker_summary",
                "role": "summarizer",
                "objective": "summarize the parent input",
                "input_context": {
                    "section": "summary",
                },
            },
            {
                "task_id": "manual_worker_checklist",
                "role": "checker",
                "objective": "produce a checklist from the parent input",
                "input_context": {
                    "section": "checklist",
                },
            },
        ],
        runtime=runtime,
    )

    worker_tasks = result.get("worker_tasks")
    if not isinstance(worker_tasks, list) or len(worker_tasks) != 2:
        return fail(f"manual decomposition should create exactly two worker tasks: {result}")
    for task in worker_tasks:
        try:
            ensure_worker_task_contract(task)
        except Exception as exc:
            return fail(f"worker_task contract failed: {exc}\n{task}")
        if task.get("parent_task_id") != parent_task["task_id"]:
            return fail(f"worker_task missing parent_task_id: {task}")
        for forbidden in ("constraints", "expected_output", "retry_policy", "planner_decision"):
            if forbidden in task:
                return fail(f"worker_task leaked strategy field {forbidden}: {task}")
    pass_step("manual split creates two contracted worker_task payloads")

    if delegated_order != ["manual_worker_summary", "manual_worker_checklist"]:
        return fail(f"runtime should execute manual workers sequentially: {delegated_order}")
    pass_step("worker_runtime executes manual workers without parallelism")

    worker_results = result.get("worker_results")
    if not isinstance(worker_results, list) or len(worker_results) != 2:
        return fail(f"manual decomposition should collect two worker results: {result}")

    snapshot = result.get("snapshot")
    try:
        ensure_worker_state_snapshot_contract(snapshot)
    except Exception as exc:
        return fail(f"snapshot contract failed: {exc}\n{snapshot}")

    if snapshot.get("active_tasks"):
        return fail(f"snapshot should have no active tasks after merge: {snapshot}")
    if len(snapshot.get("completed_tasks", [])) != 2:
        return fail(f"snapshot should contain two completed tasks: {snapshot}")
    if snapshot.get("blocked_tasks"):
        return fail(f"snapshot should not contain blocked tasks: {snapshot}")
    pass_step("merge result produces correct worker_state_snapshot")

    try:
        run_manual_decomposition(
            parent_task=parent_task,
            worker_specs=[
                {
                    "task_id": "only_one_worker",
                    "role": "worker",
                    "objective": "invalid one-worker split",
                    "input_context": {},
                }
            ],
            runtime=runtime,
        )
        return fail("manual decomposition accepted fewer than two worker specs")
    except ValueError:
        pass_step("manual decomposition rejects non-2-to-3 worker splits")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
