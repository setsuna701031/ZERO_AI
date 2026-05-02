from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.worker import (
    WorkerRuntime,
    ensure_worker_result_contract,
    ensure_worker_state_snapshot_contract,
    ensure_worker_task_contract,
)


PREFIX = "[worker-runtime-contract-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    delegated_tasks = []

    def fake_zero_runner(worker_task):
        delegated_tasks.append(worker_task)
        return {
            "ok": True,
            "status": "success",
            "summary": f"completed {worker_task['objective']}",
            "result": {
                "task_id": worker_task["task_id"],
                "handled_by": "fake_zero_runtime",
            },
            "artifacts": [
                {
                    "kind": "text",
                    "path": f"workspace/worker/{worker_task['task_id']}.txt",
                }
            ],
            "execution_trace": [
                {
                    "event_type": "delegated_runtime_call",
                    "task_id": worker_task["task_id"],
                }
            ],
            "confidence": 0.9,
        }

    runtime = WorkerRuntime(runner=fake_zero_runner)

    task_a = runtime.create_task(
        task_id="worker_task_a",
        parent_task_id="root_task",
        role="summarizer",
        objective="summarize input A",
        input_context={"input": "A"},
    )
    task_b = runtime.create_task(
        task_id="worker_task_b",
        parent_task_id="root_task",
        role="verifier",
        objective="verify input B",
        input_context={"input": "B"},
    )
    pass_step("can create two worker_task payloads")

    for task in (task_a, task_b):
        try:
            ensure_worker_task_contract(task)
        except Exception as exc:
            return fail(f"worker_task contract failed: {exc}\n{task}")
        for forbidden in ("constraints", "expected_output", "retry_policy"):
            if forbidden in task:
                return fail(f"worker_task leaked strategy field {forbidden}: {task}")
    pass_step("worker_task stays execution-only and contains no strategy fields")

    try:
        runtime.create_task(
            task_id="bad_worker_task",
            role="bad",
            objective="should fail",
            input_context={},
            retry_policy={"max_attempts": 3},
        )
        return fail("worker_task accepted retry_policy strategy field")
    except ValueError:
        pass_step("worker_task rejects strategy fields")

    results = []
    for task in (task_a, task_b):
        runner_result = runtime.run_task(task)
        if not delegated_tasks or delegated_tasks[-1] != task:
            return fail(f"run_task did not delegate the contracted worker_task: {delegated_tasks}")
        result = runtime.collect_result(task, runner_result)
        try:
            ensure_worker_result_contract(result)
        except Exception as exc:
            return fail(f"worker_result contract failed: {exc}\n{result}")
        results.append(result)
    pass_step("run_task delegates to ZERO runner and collect_result returns worker_result")

    snapshot = {}
    for result in results:
        snapshot = runtime.merge_result(result)

    try:
        ensure_worker_state_snapshot_contract(snapshot)
    except Exception as exc:
        return fail(f"worker_state_snapshot contract failed: {exc}\n{snapshot}")

    if snapshot.get("active_tasks"):
        return fail(f"snapshot should have no active tasks after merge: {snapshot}")
    if len(snapshot.get("completed_tasks", [])) != 2:
        return fail(f"snapshot should contain two completed worker results: {snapshot}")
    artifacts_index = snapshot.get("artifacts_index")
    if not isinstance(artifacts_index, dict) or sorted(artifacts_index) != ["worker_task_a", "worker_task_b"]:
        return fail(f"snapshot artifacts_index missing worker task artifacts: {snapshot}")
    pass_step("merge_result writes completed results and artifact index to state snapshot")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
