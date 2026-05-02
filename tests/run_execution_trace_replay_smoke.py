from __future__ import annotations

import copy
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.worker import (
    AggregationRuntime,
    TraceRecorder,
    TraceReplayRuntime,
    WorkerRuntime,
    WorkerScheduler,
    create_aggregation_contract,
    ensure_trace_event_contract,
    trace_digest,
)


PREFIX = "[execution-trace-replay-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    def fake_zero_runner(worker_task):
        return {
            "ok": True,
            "status": "success",
            "summary": f"done {worker_task['task_id']}",
            "result": {"task_id": worker_task["task_id"]},
            "artifacts": [{"kind": "text", "path": f"workspace/worker/{worker_task['task_id']}.txt"}],
            "trace": [{"event_type": "worker_done", "task_id": worker_task["task_id"]}],
            "confidence": 0.9,
        }

    recorder = TraceRecorder()
    runtime = WorkerRuntime(runner=fake_zero_runner)
    task_a = runtime.create_task(
        task_id="trace_worker_a",
        parent_task_id="trace_parent",
        role="a",
        objective="trace worker a",
        input_context={},
    )
    task_b = runtime.create_task(
        task_id="trace_worker_b",
        parent_task_id="trace_parent",
        role="b",
        objective="trace worker b",
        input_context={},
    )

    scheduler = WorkerScheduler(runtime=runtime, max_retries=0)
    for task in (task_a, task_b):
        queue_item = scheduler.enqueue(task)
        recorder.record(
            component="scheduler",
            event_type="enqueue",
            payload={"queue_item": queue_item},
        )

    worker_results = []
    for _ in range(2):
        recorder.record(component="scheduler", event_type="tick", payload={})
        event = scheduler.run_next()
        recorder.record(
            component="scheduler",
            event_type=str(event.get("event") or ""),
            payload={
                "task_id": event.get("task_id"),
                "queue_item": _queue_item_from_state(event.get("state"), event.get("task_id")),
            },
        )
        worker_result = event.get("worker_result")
        if isinstance(worker_result, dict):
            worker_results.append(copy.deepcopy(worker_result))
            recorder.record(
                component="worker",
                event_type="worker_result",
                payload={"worker_result": worker_result},
            )

    aggregation = AggregationRuntime(
        contract=create_aggregation_contract(
            strategy="concat",
            conflict_handling="preserve_all",
            fallback="partial_success",
        )
    )
    final_result = aggregation.aggregate(worker_results)
    recorder.record(
        component="aggregation",
        event_type="final_result",
        payload={"final_result": final_result},
    )

    events = recorder.events()
    if len(events) != 9:
        return fail(f"expected 9 trace events, got {len(events)}: {events}")
    for event in events:
        try:
            ensure_trace_event_contract(event)
        except Exception as exc:
            return fail(f"trace event schema failed: {exc}\n{event}")
    components = {event["component"] for event in events}
    if components != {"scheduler", "worker", "aggregation"}:
        return fail(f"trace should cover scheduler/worker/aggregation: {components}")
    pass_step("trace event schema covers scheduler, worker, and aggregation")

    replay = TraceReplayRuntime()
    replay_a = replay.replay(events)
    replay_b = replay.replay(copy.deepcopy(events))
    if replay_a != replay_b:
        return fail(f"same trace should replay to identical state:\n{replay_a}\n{replay_b}")
    if replay_a.get("trace_digest") != trace_digest(events):
        return fail(f"replay digest mismatch: {replay_a}")
    pass_step("same trace replays deterministically")

    replay_state = replay_a.get("scheduler_state")
    if not isinstance(replay_state, dict) or replay_state.get("queue"):
        return fail(f"replayed scheduler queue should be empty: {replay_a}")
    if len(replay_state.get("done", [])) != 2 or replay_state.get("failed"):
        return fail(f"replayed scheduler state should have two done and no failed: {replay_a}")
    if replay_state.get("tick_count") != 2:
        return fail(f"replayed scheduler tick_count should be 2: {replay_a}")
    pass_step("replay rebuilds scheduler state")

    replay_results = replay_a.get("worker_results")
    if not isinstance(replay_results, list) or len(replay_results) != 2:
        return fail(f"replay should rebuild worker results: {replay_a}")
    replay_final = replay_a.get("final_result")
    if not isinstance(replay_final, dict) or replay_final.get("source_task_ids") != ["trace_worker_a", "trace_worker_b"]:
        return fail(f"replay should rebuild final_result: {replay_a}")
    pass_step("replay rebuilds worker and aggregation outputs")

    print(f"{PREFIX} ALL PASS")
    return 0


def _queue_item_from_state(state, task_id):
    if not isinstance(state, dict):
        return {}
    for section in ("queue", "done", "failed"):
        items = state.get(section)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            task = item.get("task")
            if isinstance(task, dict) and task.get("task_id") == task_id:
                return copy.deepcopy(item)
    return {}


if __name__ == "__main__":
    raise SystemExit(main())
