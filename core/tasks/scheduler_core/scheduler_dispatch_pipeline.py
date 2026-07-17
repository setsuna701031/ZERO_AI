from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from core.tasks.scheduler_core.dispatch_helpers import build_tick_result, execute_dispatch_round
from core.tasks.scheduler_core.trace_helpers import promote_execution_trace_in_executed_results


def tick(
    scheduler: Any,
    *,
    current_tick: Optional[int] = None,
) -> Dict[str, Any]:
    scheduler.current_tick = (
        int(current_tick)
        if current_tick is not None
        else int(getattr(scheduler, "current_tick", 0)) + 1
    )

    try:
        scheduler.cleanup_task_queue_hygiene()
    except Exception:
        pass

    scheduler._unblock_tasks_if_dependencies_done()

    all_executed_results: List[Dict[str, Any]] = []
    rounds_used = 1

    last_synced = scheduler.rebuild_ready_queue()
    scheduler._apply_runtime_dispatch_gate_to_ready_queue()

    dispatch_results = scheduler.dispatcher.dispatch_until_full()
    if not dispatch_results:
        return scheduler._build_tick_result(
            rounds_used=rounds_used,
            total_dispatched=0,
            last_synced=last_synced,
            all_executed_results=[],
        )

    for dispatch_result in dispatch_results:
        scheduled_task = getattr(dispatch_result, "task", None)
        task_id = str(getattr(scheduled_task, "task_id", "") or "").strip()
        if task_id:
            scheduler._emit_scheduler_evidence(
                "dequeued",
                task_id=task_id,
                queue_name="ready",
            )

    total_dispatched = len(dispatch_results)
    round_executed = execute_dispatch_round(
        scheduler=scheduler,
        dispatch_results=dispatch_results,
        current_tick=scheduler.current_tick,
    )
    if round_executed:
        all_executed_results.extend(round_executed)

    return scheduler._build_tick_result(
        rounds_used=rounds_used,
        total_dispatched=total_dispatched,
        last_synced=last_synced,
        all_executed_results=all_executed_results,
    )


def apply_runtime_dispatch_gate_to_ready_queue(scheduler: Any) -> Dict[str, Any]:
    gated: List[Dict[str, Any]] = []
    allowed: List[str] = []

    try:
        queued_rows = scheduler.dispatcher.list_queued()
    except Exception:
        queued_rows = []

    if not isinstance(queued_rows, list):
        queued_rows = []

    for row in queued_rows:
        if not isinstance(row, dict):
            continue

        task_id = str(row.get("task_id") or "").strip()
        if not task_id:
            continue

        task = scheduler._get_task_from_repo(task_id)
        if not isinstance(task, dict):
            scheduler._cancel_ready_queue_task(task_id)
            gated.append({"task_id": task_id, "reason": "repo_task_missing"})
            continue

        task = scheduler._hydrate_task_from_workspace(task)
        decision = scheduler._runtime_dispatch_gate_decision(task)
        if decision.get("allow"):
            allowed.append(task_id)
            continue

        scheduler._cancel_ready_queue_task(task_id)
        gated.append({
            "task_id": task_id,
            "reason": decision.get("reason", "runtime_gate_blocked"),
            "status": decision.get("status", ""),
            "next_action": decision.get("next_action", ""),
            "active_blocker_count": decision.get("active_blocker_count", 0),
        })

    return {
        "ok": True,
        "allowed_task_ids": allowed,
        "gated_task_ids": [item.get("task_id") for item in gated if isinstance(item, dict)],
        "gated": gated,
    }


def build_scheduler_tick_result(
    scheduler: Any,
    *,
    scheduler_build: str,
    rounds_used: int,
    total_dispatched: int,
    last_synced: List[str],
    all_executed_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    result = build_tick_result(
        scheduler=scheduler,
        scheduler_build=scheduler_build,
        rounds_used=rounds_used,
        total_dispatched=total_dispatched,
        last_synced=last_synced,
        all_executed_results=all_executed_results,
    )

    if not isinstance(result, dict):
        return result

    executed_results = result.get("executed_results")
    if isinstance(executed_results, list):
        promoted = scheduler._promote_execution_trace_in_executed_results(executed_results)
        result["executed_results"] = promoted

        aggregated_trace: List[Dict[str, Any]] = []
        for item in promoted:
            if not isinstance(item, dict):
                continue
            trace = item.get("execution_trace")
            if isinstance(trace, list):
                aggregated_trace.extend(
                    copy.deepcopy(event) for event in trace if isinstance(event, dict)
                )

        if aggregated_trace:
            result["execution_trace"] = aggregated_trace

    return result


def promote_execution_trace(executed_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return promote_execution_trace_in_executed_results(executed_results)
