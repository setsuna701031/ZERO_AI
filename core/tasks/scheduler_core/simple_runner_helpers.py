from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from core.tools.execution_trace import ExecutionTrace


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
        return scheduler._handle_simple_terminal_task(
            task=task,
            trace=trace,
            task_id=task_id,
            task_name=task_name,
            task_status=task_status,
        )

    deps_ready, blocked_reason = scheduler._task_dependencies_satisfied(task)
    if not deps_ready:
        return scheduler._handle_simple_blocked_task(
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
        return scheduler._handle_simple_finished_task(
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
        return scheduler._handle_simple_invalid_step(
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
        return scheduler._handle_simple_step_exception(
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

    return scheduler._handle_simple_step_success(
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

def _load_simple_task_state(
    scheduler,
    task: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], int, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Any]:
    steps = task.get("steps", [])
    if not isinstance(steps, list):
        steps = []

    current_step_index = int(task.get("current_step_index", 0) or 0)

    execution_log = copy.deepcopy(task.get("execution_log", []))
    if not isinstance(execution_log, list):
        execution_log = []

    results = copy.deepcopy(task.get("results", []))
    if not isinstance(results, list):
        results = []

    step_results = copy.deepcopy(task.get("step_results", results))
    if not isinstance(step_results, list):
        step_results = copy.deepcopy(results)

    last_step_result = copy.deepcopy(task.get("last_step_result"))
    return steps, current_step_index, execution_log, results, step_results, last_step_result

def _handle_simple_terminal_task(
    scheduler,
    task: Dict[str, Any],
    trace: ExecutionTrace,
    task_id: str,
    task_name: str,
    task_status: str,
) -> Dict[str, Any]:
    scheduler._trace_status(
        trace=trace,
        task=task,
        status=task_status,
        tick=scheduler.current_tick,
        final_answer=str(task.get("final_answer") or ""),
        extra={"action": "terminal_skip"},
    )
    scheduler._save_trace_for_task(task=task, trace=trace)
    return {
        "ok": True,
        "action": "terminal_skip",
        "tick": scheduler.current_tick,
        "task_id": task_id,
        "task_name": task_name,
        "status": task_status,
        "message": "task already terminal",
        "final_answer": task.get("final_answer", ""),
    }

def _handle_simple_blocked_task(
    scheduler,
    task: Dict[str, Any],
    trace: ExecutionTrace,
    task_id: str,
    task_name: str,
    blocked_reason: str,
) -> Dict[str, Any]:
    blocked_status = getattr(scheduler, "STATUS_BLOCKED", "blocked")
    task["status"] = blocked_status
    task["blocked_reason"] = blocked_reason
    task["history"] = scheduler._append_history(task.get("history"), blocked_status)

    scheduler._trace_status(
        trace=trace,
        task=task,
        status=blocked_status,
        tick=scheduler.current_tick,
        final_answer="",
        extra={
            "action": "blocked_by_dependencies",
            "blocked_reason": blocked_reason,
        },
    )
    scheduler._save_trace_for_task(task=task, trace=trace)

    return {
        "ok": False,
        "action": "blocked_by_dependencies",
        "tick": scheduler.current_tick,
        "task_id": task_id,
        "task_name": task_name,
        "status": blocked_status,
        "blocked_reason": blocked_reason,
        "error": blocked_reason,
    }

def _handle_simple_finished_task(
    scheduler,
    task: Dict[str, Any],
    trace: ExecutionTrace,
    task_id: str,
    task_name: str,
    current_step_index: int,
    steps: List[Dict[str, Any]],
    execution_log: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    step_results: List[Dict[str, Any]],
    last_step_result: Any,
) -> Dict[str, Any]:
    task["status"] = "finished"
    task["final_answer"] = str(task.get("final_answer") or scheduler._build_simple_final_answer(results))
    task["finished_tick"] = scheduler.current_tick
    task["last_run_tick"] = scheduler.current_tick
    task["results"] = results
    task["step_results"] = step_results
    task["last_step_result"] = last_step_result
    task["history"] = scheduler._append_history(task.get("history"), "finished")

    scheduler._trace_status(
        trace=trace,
        task=task,
        status="finished",
        tick=scheduler.current_tick,
        final_answer=task["final_answer"],
        extra={
            "action": "simple_task_finished",
            "current_step_index": current_step_index,
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
        "final_answer": task["final_answer"],
        "execution_log": execution_log,
        "results": results,
        "step_results": step_results,
        "last_step_result": last_step_result,
        "current_step_index": current_step_index,
        "step_count": len(steps),
        "steps_total": len(steps),
        "last_run_tick": scheduler.current_tick,
        "finished_tick": scheduler.current_tick,
    }

def _handle_simple_invalid_step(
    scheduler,
    task: Dict[str, Any],
    trace: ExecutionTrace,
    task_id: str,
    task_name: str,
    results: List[Dict[str, Any]],
    step_results: List[Dict[str, Any]],
    last_step_result: Any,
) -> Dict[str, Any]:
    task["status"] = "failed"
    task["last_error"] = "invalid step type"
    task["failure_message"] = "invalid step type"
    task["last_failure_tick"] = scheduler.current_tick
    task["last_run_tick"] = scheduler.current_tick
    task["results"] = results
    task["step_results"] = step_results
    task["last_step_result"] = last_step_result
    task["history"] = scheduler._append_history(task.get("history"), "failed")

    scheduler._trace_status(
        trace=trace,
        task=task,
        status="failed",
        tick=scheduler.current_tick,
        final_answer="",
        extra={
            "action": "simple_invalid_step",
            "error": "invalid step type",
        },
    )
    scheduler._save_trace_for_task(task=task, trace=trace)

    return {
        "ok": False,
        "action": "simple_invalid_step",
        "tick": scheduler.current_tick,
        "task_id": task_id,
        "task_name": task_name,
        "status": "failed",
        "message": "invalid step type",
        "error": "invalid step type",
    }

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

    scheduler._trace_step(
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
        task["status"] = "queued"
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

    task["status"] = "failed"
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

    scheduler._trace_step(
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
        task["status"] = "finished"
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

    task["status"] = "queued"
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
