from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from core.tasks.scheduler_core.retrying_repair_replay_state import (
    repair_replacement_decision,
    replay_continuation_fields,
)


BuildRepairSteps = Callable[[Dict[str, Any], Dict[str, Any]], Any]
PersistTaskPayload = Callable[..., Any]
WriteRuntimeState = Callable[[Dict[str, Any], Dict[str, Any]], None]
NowProvider = Callable[[], str]


def safe_repair_injection_now() -> str:
    try:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def normalize_repair_injection_mutation(
    *,
    task: Dict[str, Any],
    runtime_state: Any,
    repair_context: Dict[str, Any],
    steps: List[Dict[str, Any]],
    step_index: int,
    repair_steps: List[Dict[str, Any]],
    repair_meta: Dict[str, Any],
    current_tick: Optional[int],
    now: str,
) -> Dict[str, Any]:
    new_steps = copy.deepcopy(steps[:step_index]) + copy.deepcopy(repair_steps)
    if step_index + 1 < len(steps):
        new_steps.extend(copy.deepcopy(steps[step_index + 1:]))

    repair_context = copy.deepcopy(repair_context)
    flow = repair_context.get("flow") if isinstance(repair_context.get("flow"), list) else []
    flow.append(
        {
            "phase": "repair_steps_injected",
            "ok": True,
            "tick": current_tick,
            "ts": now,
            "strategy": "minimal_patch",
            "step_index": step_index,
            "inserted_steps": [step.get("id") for step in repair_steps if isinstance(step, dict)],
            "target_path": repair_meta.get("relative_path") or repair_meta.get("path") or "",
        }
    )
    repair_context["flow"] = flow[-50:]
    repair_context["repair_steps_injected"] = True
    repair_context["last_phase"] = "repair_steps_injected"
    repair_context["proposed_fix"] = {
        "strategy": "minimal_patch",
        "path": repair_meta.get("path", ""),
        "relative_path": repair_meta.get("relative_path", ""),
        "reason": repair_meta.get("reason", ""),
    }

    task["steps"] = new_steps
    task["steps_total"] = len(new_steps)
    task["current_step_index"] = step_index
    task.update(replay_continuation_fields())
    task["repair_context"] = repair_context
    task["repair_steps_injected"] = True
    task["updated_at"] = now

    if isinstance(runtime_state, dict):
        runtime_state.update(
            {
                "steps": copy.deepcopy(new_steps),
                "steps_total": len(new_steps),
                "current_step_index": step_index,
                "status": "queued",
                "next_action": "run_next_tick",
                "last_decision": "continue",
                "last_decision_reason": "repair_steps_injected",
                "repair_context": copy.deepcopy(repair_context),
                "updated_at": now,
            }
        )

    return {
        "task": task,
        "runtime_state": runtime_state,
        "repair_context": repair_context,
        "new_steps": new_steps,
    }


def execute_repair_injection_transaction(
    *,
    task: Dict[str, Any],
    task_id: str,
    runtime_state: Any,
    repair_context: Dict[str, Any],
    steps: List[Dict[str, Any]],
    step_index: int,
    failed_step: Dict[str, Any],
    current_tick: Optional[int],
    build_retry_repair_steps: BuildRepairSteps,
    write_runtime_state: WriteRuntimeState,
    persist_task_payload: PersistTaskPayload,
    status_failed: str,
    now_provider: NowProvider = safe_repair_injection_now,
) -> Dict[str, Any]:
    ok, repair_steps, repair_meta = build_retry_repair_steps(task, failed_step)
    replacement_decision = repair_replacement_decision(ok, repair_steps, repair_meta)
    repair_meta = replacement_decision["repair_meta"]
    if replacement_decision["action"] == "repair_injection_failed":
        task["status"] = status_failed
        task["last_error"] = "retrying repair bridge failed: " + str(repair_meta.get("reason") or "unknown")
        task["failure_message"] = task["last_error"]
        persist_task_payload(task_id=task_id, task=task)
        return {
            "result": {
                "ok": False,
                "action": "retrying_repair_bridge_failed",
                "status": status_failed,
                "task_id": task_id,
                "error": task["last_error"],
                "repair_meta": repair_meta,
                "task": copy.deepcopy(task),
            },
            "enqueue_action": replacement_decision["action"],
        }

    repair_steps = replacement_decision["repair_steps"]
    now = now_provider()
    mutation = normalize_repair_injection_mutation(
        task=task,
        runtime_state=runtime_state,
        repair_context=repair_context,
        steps=steps,
        step_index=step_index,
        repair_steps=repair_steps,
        repair_meta=repair_meta,
        current_tick=current_tick,
        now=now,
    )

    task = mutation["task"]
    runtime_state = mutation["runtime_state"]
    new_steps = mutation["new_steps"]
    if isinstance(runtime_state, dict):
        write_runtime_state(task, runtime_state)

    persist_task_payload(task_id=task_id, task=task)
    return {
        "result": {
            "ok": True,
            "action": "repair_steps_injected",
            "status": "queued",
            "task_id": task_id,
            "current_step_index": step_index,
            "steps_total": len(new_steps),
            "inserted_steps": [step.get("id") for step in repair_steps if isinstance(step, dict)],
            "repair_meta": {
                "reason": repair_meta.get("reason", ""),
                "relative_path": repair_meta.get("relative_path", ""),
                "cwd": repair_meta.get("cwd", ""),
            },
            "task": copy.deepcopy(task),
        },
        "enqueue_action": replacement_decision["action"],
    }
