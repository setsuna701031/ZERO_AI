from __future__ import annotations

import copy
from typing import Any, Callable, Dict

from core.runtime.runtime_status_canonicalization import canonical_runtime_status


def prepare_step_execution(
    *,
    runtime: Any,
    task: Dict[str, Any],
    current_tick: int,
    ensure_execution_trace_defaults: Callable[[Dict[str, Any], Dict[str, Any]], None],
    maybe_block_direct_missing_subgoal_dependency: Callable[..., Any],
    safe_block_engineering_action: Callable[..., None],
    terminal_completion_authority: Callable[..., Any],
) -> Dict[str, Any]:
    state = runtime.load_runtime_state(task)
    ensure_execution_trace_defaults(task, state)

    steps = state.get("steps", [])
    idx = int(state.get("current_step_index", 0) or 0)

    if not isinstance(steps, list):
        steps = []

    if idx >= len(steps):
        last_result = task.get("last_step_result") or state.get("last_step_result")
        last_payload = last_result.get("result") if isinstance(last_result, dict) else {}
        last_step = last_result.get("step") if isinstance(last_result, dict) else {}
        finish_result = runtime.mark_finished(
            task=task,
            current_tick=current_tick,
            final_answer=str(task.get("final_answer") or state.get("final_answer") or ""),
            final_result=copy.deepcopy(task.get("last_step_result") or state.get("last_step_result")),
            completion_authority=terminal_completion_authority(
                task=task,
                step=last_step,
                result=last_payload,
            ),
        )
        runtime_state = copy.deepcopy(finish_result.get("runtime_state", {}))
        ensure_execution_trace_defaults(task, runtime_state)
        return {
            "continue_execution": False,
            "terminal_result": {
                "ok": True,
                "action": "already_finished",
                "task": copy.deepcopy(task),
                "runtime_state": runtime_state,
                "status": "finished",
                "final_answer": finish_result.get("final_answer", ""),
                "task_completion_authority": finish_result.get("task_completion_authority"),
            },
            "task": task,
            "state": runtime_state,
            "steps": steps,
            "step_index": idx,
            "prepare_result": None,
        }

    direct_block = maybe_block_direct_missing_subgoal_dependency(
        task=task,
        state=state,
        step_index=idx,
        current_tick=current_tick,
    )
    if isinstance(direct_block, dict):
        return {
            "continue_execution": False,
            "terminal_result": direct_block,
            "task": task,
            "state": state,
            "steps": steps,
            "step_index": idx,
            "prepare_result": None,
        }

    prepare_result = runtime.prepare_current_subgoal(task=task, current_tick=current_tick)
    prepared_state = copy.deepcopy(prepare_result.get("runtime_state", state))
    ensure_execution_trace_defaults(task, prepared_state)
    if not bool(prepare_result.get("ok", False)):
        safe_block_engineering_action(
            task=task,
            step=steps[idx] if isinstance(steps, list) and 0 <= idx < len(steps) else {},
            step_result=copy.deepcopy(prepare_result),
            step_index=idx,
            current_tick=current_tick,
            trace_tick=current_tick,
            reason=str(prepare_result.get("reason") or prepared_state.get("last_error") or "subgoal blocked"),
        )
        return {
            "continue_execution": False,
            "terminal_result": {
                "ok": False,
                "action": "subgoal_blocked",
                "task": copy.deepcopy(task),
                "runtime_state": prepared_state,
                "status": prepared_state.get("status", "blocked"),
                "error": prepare_result.get("reason") or prepared_state.get("last_error"),
                "execution_trace": copy.deepcopy(prepared_state.get("execution_trace", [])),
            },
            "task": task,
            "state": prepared_state,
            "steps": steps,
            "step_index": idx,
            "prepare_result": prepare_result,
        }
    if canonical_runtime_status(prepared_state.get("status")) == "completed":
        return {
            "continue_execution": False,
            "terminal_result": {
                "ok": True,
                "action": "already_finished",
                "task": copy.deepcopy(task),
                "runtime_state": prepared_state,
                "status": "finished",
                "final_answer": str(prepared_state.get("final_answer") or ""),
                "execution_trace": copy.deepcopy(prepared_state.get("execution_trace", [])),
            },
            "task": task,
            "state": prepared_state,
            "steps": steps,
            "step_index": idx,
            "prepare_result": prepare_result,
        }

    state = prepared_state
    steps = state.get("steps", []) if isinstance(state.get("steps"), list) else []
    idx = int(state.get("current_step_index", idx) or idx)

    return {
        "continue_execution": True,
        "terminal_result": None,
        "task": task,
        "state": state,
        "steps": steps,
        "step_index": idx,
        "prepare_result": prepare_result,
    }


__all__ = ["prepare_step_execution"]
