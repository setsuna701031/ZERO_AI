from __future__ import annotations

from core.runtime.task_runtime import project_runtime_status
import copy
from typing import Any, Dict, List, Optional, Tuple

from core.tools.execution_trace import ExecutionTrace
from core.tasks.scheduler_core.trace_helpers import trace_step


def _run_simple_task_tick(
    scheduler,
    task: Dict[str, Any],
    current_tick: Optional[int] = None,
) -> Dict[str, Any]:
    if current_tick is not None:
        scheduler.current_tick = int(current_tick)

    task = scheduler._hydrate_task_from_workspace(task)

    task_id = scheduler._extract_task_id(task)
    task_name = str(task.get("task_name") or task_id or "unknown_task")
    task_status = str(task.get("status") or "").strip().lower()
    trace = scheduler._load_trace_for_task(task)

    if task_status in getattr(scheduler, "TERMINAL_STATUSES", set()):
        return _handle_simple_terminal_task(
            scheduler=scheduler,
            task=task,
            trace=trace,
            task_id=task_id,
            task_name=task_name,
            task_status=task_status,
        )

    deps_ready, blocked_reason = scheduler._task_dependencies_satisfied(task)
    if not deps_ready:
        return _handle_simple_blocked_task(
            scheduler=scheduler,
            task=task,
            trace=trace,
            task_id=task_id,
            task_name=task_name,
            blocked_reason=blocked_reason,
        )

    steps, current_step_index, execution_log, results, step_results, last_step_result = (
        scheduler._load_simple_task_state(task)
    )

    if current_step_index >= len(steps):
        return _handle_simple_finished_task(
            scheduler=scheduler,
            task=task,
            trace=trace,
            task_id=task_id,
            task_name=task_name,
            current_step_index=current_step_index,
            steps=steps,
            execution_log=execution_log,
            results=results,
            step_results=step_results,
            last_step_result=last_step_result,
        )

    step = steps[current_step_index]
    if not isinstance(step, dict):
        return _handle_simple_invalid_step(
            scheduler=scheduler,
            task=task,
            trace=trace,
            task_id=task_id,
            task_name=task_name,
            results=results,
            step_results=step_results,
            last_step_result=last_step_result,
        )

    try:
        step_result = scheduler._execute_simple_step(task=task, step=step)
    except Exception as e:
        return _handle_simple_step_exception(
            scheduler=scheduler,
            task=task,
            trace=trace,
            task_id=task_id,
            task_name=task_name,
            current_step_index=current_step_index,
            step=step,
            error=e,
            execution_log=execution_log,
            results=results,
            step_results=step_results,
            last_step_result=last_step_result,
        )

    return _handle_simple_step_success(
        scheduler=scheduler,
        task=task,
        trace=trace,
        task_id=task_id,
        task_name=task_name,
        current_step_index=current_step_index,
        step=step,
        step_result=step_result,
        steps=steps,
        execution_log=execution_log,
        results=results,
        step_results=step_results,
        last_step_result=last_step_result,
    )

from .simple_runner_state import _load_simple_task_state
from .simple_runner_terminal import _handle_simple_terminal_task
from .simple_runner_blocked import _handle_simple_blocked_task
from .simple_runner_finished import _handle_simple_finished_task
from .simple_runner_invalid import _handle_simple_invalid_step
def _handle_simple_step_exception(
    scheduler,
    task: Dict[str, Any],
    trace: ExecutionTrace,
    task_id: str,
    task_name: str,
    current_step_index: int,
    step: Dict[str, Any],
    error: Exception,
    execution_log: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    step_results: List[Dict[str, Any]],
    last_step_result: Any,
) -> Dict[str, Any]:
    failed_step_result = {
        "ok": False,
        "step_index": current_step_index,
        "step": copy.deepcopy(step),
        "error": str(error),
    }
    execution_log.append(
        {
            "tick": scheduler.current_tick,
            "step_index": current_step_index,
            "step": copy.deepcopy(step),
            "ok": False,
            "error": str(error),
        }
    )
    results.append(copy.deepcopy(failed_step_result))
    step_results = copy.deepcopy(results)
    last_step_result = copy.deepcopy(failed_step_result)

    task["execution_log"] = execution_log
    task["results"] = results
    task["step_results"] = step_results
    task["last_step_result"] = last_step_result
    task["last_error"] = str(error)
    task["failure_message"] = str(error)
    task["last_failure_tick"] = scheduler.current_tick
    task["last_run_tick"] = scheduler.current_tick

    trace_step(
        scheduler=scheduler,
        trace=trace,
        task=task,
        step_index=current_step_index,
        step=step,
        ok=False,
        result=None,
        error=str(error),
        tick=scheduler.current_tick,
    )

    replan_result = scheduler._try_replan_task(task=task)
    task["replan_decision"] = str(replan_result.get("decision") or "")
    task["replan_summary"] = str(replan_result.get("summary") or "")
    task["replan_failed_step_type"] = str(replan_result.get("failed_step_type") or "")
    task["replan_repairable"] = replan_result.get("repairable", None)

    if replan_result.get("replanned"):
        project_runtime_status(task, "queued", owner="core/tasks/scheduler_core/simple_runner_helpers.py")
        task["replan_reason"] = str(task.get("last_error") or task.get("failure_message") or str(error))
        task["current_step_index"] = 0
        task["history"] = scheduler._append_history(task.get("history"), "replanned")
        task["history"] = scheduler._append_history(task.get("history"), "queued")

        new_steps = task.get("steps", []) if isinstance(task.get("steps"), list) else []
        new_steps_total = len(new_steps)

        scheduler._trace_replan(
            trace=trace,
            task=task,
            tick=scheduler.current_tick,
            replan_result=replan_result,
        )
        scheduler._trace_status(
            trace=trace,
            task=task,
            status="queued",
            tick=scheduler.current_tick,
            final_answer="",
            extra={
                "action": "simple_step_replanned",
                "replan_reason": task["replan_reason"],
                "replan_count": task.get("replan_count", 0),
                "replan_decision": task.get("replan_decision", ""),
                "replan_summary": task.get("replan_summary", ""),
                "replan_failed_step_type": task.get("replan_failed_step_type", ""),
                "replan_repairable": task.get("replan_repairable", None),
                "steps_total": new_steps_total,
            },
        )
        scheduler._save_trace_for_task(task=task, trace=trace)

        return {
            "ok": True,
            "action": "simple_step_replanned",
            "tick": scheduler.current_tick,
            "task_id": task_id,
            "task_name": task_name,
            "status": "queued",
            "message": replan_result.get("summary", "task replanned"),
            "execution_log": execution_log,
            "results": results,
            "step_results": step_results,
            "last_step_result": last_step_result,
            "current_step_index": 0,
            "step_count": new_steps_total,
            "steps_total": new_steps_total,
            "last_run_tick": scheduler.current_tick,
            "last_failure_tick": scheduler.current_tick,
            "replan_reason": task["replan_reason"],
            "replan_decision": task.get("replan_decision", ""),
            "replan_summary": task.get("replan_summary", ""),
            "replan_failed_step_type": task.get("replan_failed_step_type", ""),
            "replan_repairable": task.get("replan_repairable", None),
            "replan_result": replan_result,
        }

    project_runtime_status(task, "failed", owner="core/tasks/scheduler_core/simple_runner_helpers.py")
    task["history"] = scheduler._append_history(task.get("history"), "failed")

    scheduler._trace_status(
        trace=trace,
        task=task,
        status="failed",
        tick=scheduler.current_tick,
        final_answer="",
        extra={
            "action": "simple_step_failed",
            "error": str(error),
            "replan_decision": task.get("replan_decision", ""),
            "replan_summary": task.get("replan_summary", ""),
            "replan_failed_step_type": task.get("replan_failed_step_type", ""),
            "replan_repairable": task.get("replan_repairable", None),
            "replan_result": copy.deepcopy(replan_result),
        },
    )
    scheduler._save_trace_for_task(task=task, trace=trace)

    return {
        "ok": False,
        "action": "simple_step_failed",
        "tick": scheduler.current_tick,
        "task_id": task_id,
        "task_name": task_name,
        "status": "failed",
        "message": "step execution failed",
        "error": str(error),
        "execution_log": execution_log,
        "results": results,
        "step_results": step_results,
        "last_step_result": last_step_result,
        "current_step_index": current_step_index,
        "step_count": len(task.get("steps", [])) if isinstance(task.get("steps"), list) else 0,
        "steps_total": len(task.get("steps", [])) if isinstance(task.get("steps"), list) else 0,
        "last_run_tick": scheduler.current_tick,
        "last_failure_tick": scheduler.current_tick,
        "replan_decision": task.get("replan_decision", ""),
        "replan_summary": task.get("replan_summary", ""),
        "replan_failed_step_type": task.get("replan_failed_step_type", ""),
        "replan_repairable": task.get("replan_repairable", None),
        "replan_result": replan_result,
    }


def _extract_simple_step_failure_signal(payload: Any, *, max_depth: int = 5) -> Dict[str, Any]:
    """Return a compact failure/block signal from a step result payload.

    Scheduler simple-runner must not treat a blocked or failed executor result as
    success.  StepExecutor/gateway payloads can be nested, so this helper checks
    both top-level and common nested result/error containers without copying large
    evidence payloads.
    """
    if max_depth <= 0:
        return {"failed": False, "blocked": False, "message": "", "error_type": ""}

    if not isinstance(payload, dict):
        return {"failed": False, "blocked": False, "message": "", "error_type": ""}

    error_payload = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    error_type = str(
        payload.get("error_type")
        or payload.get("failure_type")
        or error_payload.get("type")
        or ""
    ).strip()
    message = str(
        payload.get("message")
        or payload.get("final_answer")
        or payload.get("last_error")
        or payload.get("failure_message")
        or error_payload.get("message")
        or payload.get("error")
        or ""
    ).strip()

    status = str(payload.get("status") or "").strip().lower()
    action = str(payload.get("action") or "").strip().lower()

    blocked = bool(payload.get("blocked")) or status in {
        "blocked",
        "review_required",
        "waiting",
        "waiting_review",
        "waiting_blocker",
    }
    failed = (
        payload.get("ok") is False
        or bool(payload.get("failed"))
        or status in {"failed", "error", "cancelled", "canceled"}
        or action in {"step_failed", "simple_step_failed", "execution_failed"}
    )

    if error_type in {
        "execution_authority_denied",
        "authority_denied",
        "permission_denied",
        "unsafe_action_blocked",
        "repo_scope_confirmation_required",
    }:
        blocked = True
        failed = True

    if blocked or failed:
        return {
            "failed": bool(failed),
            "blocked": bool(blocked),
            "message": message or error_type or status or action or "step execution blocked",
            "error_type": error_type,
        }

    for key in ("runtime_execution_result", "result", "adapter_payload", "raw"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            signal = _extract_simple_step_failure_signal(nested, max_depth=max_depth - 1)
            if signal.get("failed") or signal.get("blocked"):
                return signal

    return {"failed": False, "blocked": False, "message": "", "error_type": ""}


def _handle_simple_step_blocked_or_failed_result(
    scheduler,
    task: Dict[str, Any],
    trace: ExecutionTrace,
    task_id: str,
    task_name: str,
    current_step_index: int,
    step: Dict[str, Any],
    step_result: Dict[str, Any],
    steps: List[Dict[str, Any]],
    execution_log: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    step_results: List[Dict[str, Any]],
    last_step_result: Any,
    failure_signal: Dict[str, Any],
) -> Dict[str, Any]:
    blocked = bool(failure_signal.get("blocked"))
    error_type = str(failure_signal.get("error_type") or "step_execution_failed")
    message = str(failure_signal.get("message") or error_type or "step execution failed")
    status = getattr(scheduler, "STATUS_BLOCKED", "blocked") if blocked else "failed"
    action = "simple_step_blocked" if blocked else "simple_step_failed"

    normalized_step_result = {
        "ok": False,
        "step_index": current_step_index,
        "step_type": str(step.get("type") or step.get("action") or "").strip().lower(),
        "step": copy.deepcopy(step),
        "result": copy.deepcopy(step_result),
        "blocked": blocked,
        "failed": not blocked,
        "error_type": error_type,
        "message": message,
        "final_answer": message,
        "error": {
            "type": error_type,
            "message": message,
            "retryable": False,
        },
    }

    execution_log.append(
        {
            "tick": scheduler.current_tick,
            "step_index": current_step_index,
            "step": copy.deepcopy(step),
            "ok": False,
            "blocked": blocked,
            "failed": not blocked,
            "error_type": error_type,
            "message": message,
            "result": copy.deepcopy(step_result),
        }
    )
    results.append(copy.deepcopy(normalized_step_result))
    step_results = copy.deepcopy(results)
    last_step_result = copy.deepcopy(normalized_step_result)

    project_runtime_status(task, status, owner="core/tasks/scheduler_core/simple_runner_helpers.py")
    task["execution_log"] = execution_log
    task["results"] = results
    task["step_results"] = step_results
    task["last_step_result"] = last_step_result
    task["last_error"] = message
    task["failure_message"] = message
    task["failure_type"] = error_type
    task["state_detail"] = message
    task["last_run_tick"] = scheduler.current_tick
    task["current_step_index"] = current_step_index
    if blocked:
        task["blocked_reason"] = message
        task["next_action"] = "wait_for_external_event"
    else:
        task["last_failure_tick"] = scheduler.current_tick
    task["history"] = scheduler._append_history(task.get("history"), status)

    trace_step(
        scheduler=scheduler,
        trace=trace,
        task=task,
        step_index=current_step_index,
        step=step,
        ok=False,
        result=step_result,
        error=message,
        tick=scheduler.current_tick,
    )
    scheduler._trace_status(
        trace=trace,
        task=task,
        status=status,
        tick=scheduler.current_tick,
        final_answer="",
        extra={
            "action": action,
            "error": message,
            "error_type": error_type,
            "blocked": blocked,
            "current_step_index": current_step_index,
            "steps_total": len(steps),
        },
    )
    scheduler._save_trace_for_task(task=task, trace=trace)

    return {
        "ok": False,
        "action": action,
        "tick": scheduler.current_tick,
        "task_id": task_id,
        "task_name": task_name,
        "status": status,
        "message": message,
        "final_answer": "",
        "error": copy.deepcopy(normalized_step_result["error"]),
        "blocked": blocked,
        "failed": not blocked,
        "error_type": error_type,
        "execution_log": execution_log,
        "results": results,
        "step_results": step_results,
        "last_step_result": last_step_result,
        "current_step_index": current_step_index,
        "step_count": len(steps),
        "steps_total": len(steps),
        "last_run_tick": scheduler.current_tick,
        "last_failure_tick": scheduler.current_tick if not blocked else None,
    }

def _handle_simple_step_success(
    scheduler,
    task: Dict[str, Any],
    trace: ExecutionTrace,
    task_id: str,
    task_name: str,
    current_step_index: int,
    step: Dict[str, Any],
    step_result: Dict[str, Any],
    steps: List[Dict[str, Any]],
    execution_log: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    step_results: List[Dict[str, Any]],
    last_step_result: Any,
) -> Dict[str, Any]:
    failure_signal = _extract_simple_step_failure_signal(step_result)
    if failure_signal.get("failed") or failure_signal.get("blocked"):
        return _handle_simple_step_blocked_or_failed_result(
            scheduler=scheduler,
            task=task,
            trace=trace,
            task_id=task_id,
            task_name=task_name,
            current_step_index=current_step_index,
            step=step,
            step_result=step_result,
            steps=steps,
            execution_log=execution_log,
            results=results,
            step_results=step_results,
            last_step_result=last_step_result,
            failure_signal=failure_signal,
        )

    normalized_step_result = {
        "ok": True,
        "step_index": current_step_index,
        "step": copy.deepcopy(step),
        "result": copy.deepcopy(step_result),
    }

    execution_log.append(
        {
            "tick": scheduler.current_tick,
            "step_index": current_step_index,
            "step": copy.deepcopy(step),
            "ok": True,
            "result": copy.deepcopy(step_result),
        }
    )
    results.append(copy.deepcopy(normalized_step_result))
    step_results = copy.deepcopy(results)
    last_step_result = copy.deepcopy(normalized_step_result)

    task["execution_log"] = execution_log
    task["results"] = results
    task["step_results"] = step_results
    task["last_step_result"] = last_step_result
    task["current_step_index"] = current_step_index + 1
    task["last_run_tick"] = scheduler.current_tick

    trace_step(
        scheduler=scheduler,
        trace=trace,
        task=task,
        step_index=current_step_index,
        step=step,
        ok=True,
        result=step_result,
        error="",
        tick=scheduler.current_tick,
    )

    if task["current_step_index"] >= len(steps):
        final_answer = scheduler._build_simple_final_answer(
            [x.get("result", x) if isinstance(x, dict) else x for x in results]
        )
        project_runtime_status(task, "finished", owner="core/tasks/scheduler_core/simple_runner_helpers.py")
        task["final_answer"] = final_answer
        task["finished_tick"] = scheduler.current_tick
        task["history"] = scheduler._append_history(task.get("history"), "finished")

        scheduler._trace_status(
            trace=trace,
            task=task,
            status="finished",
            tick=scheduler.current_tick,
            final_answer=final_answer,
            extra={
                "action": "simple_task_finished",
                "current_step_index": task["current_step_index"],
                "steps_total": len(steps),
            },
        )
        scheduler._save_trace_for_task(task=task, trace=trace)

        return {
            "ok": True,
            "action": "simple_task_finished",
            "tick": scheduler.current_tick,
            "task_id": task_id,
            "task_name": task_name,
            "status": "finished",
            "message": "task finished",
            "final_answer": final_answer,
            "execution_log": execution_log,
            "results": results,
            "step_results": step_results,
            "last_step_result": last_step_result,
            "current_step_index": task["current_step_index"],
            "step_count": len(steps),
            "steps_total": len(steps),
            "last_run_tick": scheduler.current_tick,
            "finished_tick": scheduler.current_tick,
        }

    project_runtime_status(task, "queued", owner="core/tasks/scheduler_core/simple_runner_helpers.py")
    task["history"] = scheduler._append_history(task.get("history"), "queued")

    scheduler._trace_status(
        trace=trace,
        task=task,
        status="queued",
        tick=scheduler.current_tick,
        final_answer="",
        extra={
            "action": "simple_step_executed",
            "current_step_index": task["current_step_index"],
            "steps_total": len(steps),
        },
    )
    scheduler._save_trace_for_task(task=task, trace=trace)

    return {
        "ok": True,
        "action": "simple_step_executed",
        "tick": scheduler.current_tick,
        "task_id": task_id,
        "task_name": task_name,
        "status": "queued",
        "message": "step executed, waiting next tick",
        "final_answer": "",
        "execution_log": execution_log,
        "results": results,
        "step_results": step_results,
        "last_step_result": last_step_result,
        "current_step_index": task["current_step_index"],
        "step_count": len(steps),
        "steps_total": len(steps),
        "last_run_tick": scheduler.current_tick,
    }



# public exports used by scheduler.py
run_simple_task_tick = _run_simple_task_tick
load_simple_task_state = _load_simple_task_state
handle_simple_terminal_task = _handle_simple_terminal_task
handle_simple_blocked_task = _handle_simple_blocked_task
handle_simple_finished_task = _handle_simple_finished_task
handle_simple_invalid_step = _handle_simple_invalid_step
handle_simple_step_exception = _handle_simple_step_exception
handle_simple_step_success = _handle_simple_step_success
