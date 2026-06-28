from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple


def _build_simple_failed_step_result(
    current_step_index: int,
    step: Dict[str, Any],
    error: Exception,
) -> Dict[str, Any]:
    return {
        "ok": False,
        "step_index": current_step_index,
        "step": copy.deepcopy(step),
        "error": str(error),
    }


def _build_simple_success_step_result(
    current_step_index: int,
    step: Dict[str, Any],
    step_result: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "ok": True,
        "step_index": current_step_index,
        "step": copy.deepcopy(step),
        "result": copy.deepcopy(step_result),
    }


def _sync_simple_failed_step_collections(
    *,
    tick: int,
    current_step_index: int,
    step: Dict[str, Any],
    error: Exception,
    execution_log: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    failed_step_result: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Any]:
    execution_log.append(
        {
            "tick": tick,
            "step_index": current_step_index,
            "step": copy.deepcopy(step),
            "ok": False,
            "error": str(error),
        }
    )
    results.append(copy.deepcopy(failed_step_result))
    step_results = copy.deepcopy(results)
    last_step_result = copy.deepcopy(failed_step_result)
    return step_results, last_step_result


def _sync_simple_success_step_collections(
    *,
    tick: int,
    current_step_index: int,
    step: Dict[str, Any],
    step_result: Dict[str, Any],
    execution_log: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    normalized_step_result: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Any]:
    execution_log.append(
        {
            "tick": tick,
            "step_index": current_step_index,
            "step": copy.deepcopy(step),
            "ok": True,
            "result": copy.deepcopy(step_result),
        }
    )
    results.append(copy.deepcopy(normalized_step_result))
    step_results = copy.deepcopy(results)
    last_step_result = copy.deepcopy(normalized_step_result)
    return step_results, last_step_result


def _build_simple_step_replanned_payload(
    *,
    tick: int,
    task_id: str,
    task_name: str,
    message: str,
    execution_log: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    step_results: List[Dict[str, Any]],
    last_step_result: Any,
    steps_total: int,
    replan_reason: str,
    replan_decision: str,
    replan_summary: str,
    replan_failed_step_type: str,
    replan_repairable: Any,
    replan_result: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "ok": True,
        "action": "simple_step_replanned",
        "tick": tick,
        "task_id": task_id,
        "task_name": task_name,
        "status": "queued",
        "message": message,
        "execution_log": execution_log,
        "results": results,
        "step_results": step_results,
        "last_step_result": last_step_result,
        "current_step_index": 0,
        "step_count": steps_total,
        "steps_total": steps_total,
        "last_run_tick": tick,
        "last_failure_tick": tick,
        "replan_reason": replan_reason,
        "replan_decision": replan_decision,
        "replan_summary": replan_summary,
        "replan_failed_step_type": replan_failed_step_type,
        "replan_repairable": replan_repairable,
        "replan_result": replan_result,
    }


def _build_simple_step_failed_payload(
    *,
    tick: int,
    task_id: str,
    task_name: str,
    error: Exception,
    execution_log: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    step_results: List[Dict[str, Any]],
    last_step_result: Any,
    current_step_index: int,
    step_count: int,
    replan_decision: str,
    replan_summary: str,
    replan_failed_step_type: str,
    replan_repairable: Any,
    replan_result: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "ok": False,
        "action": "simple_step_failed",
        "tick": tick,
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
        "step_count": step_count,
        "steps_total": step_count,
        "last_run_tick": tick,
        "last_failure_tick": tick,
        "replan_decision": replan_decision,
        "replan_summary": replan_summary,
        "replan_failed_step_type": replan_failed_step_type,
        "replan_repairable": replan_repairable,
        "replan_result": replan_result,
    }


def _build_simple_task_finished_payload(
    *,
    tick: int,
    task_id: str,
    task_name: str,
    final_answer: str,
    execution_log: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    step_results: List[Dict[str, Any]],
    last_step_result: Any,
    current_step_index: int,
    step_count: int,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "action": "simple_task_finished",
        "tick": tick,
        "task_id": task_id,
        "task_name": task_name,
        "status": "finished",
        "message": "task finished",
        "final_answer": final_answer,
        "execution_log": execution_log,
        "results": results,
        "step_results": step_results,
        "last_step_result": last_step_result,
        "current_step_index": current_step_index,
        "step_count": step_count,
        "steps_total": step_count,
        "last_run_tick": tick,
        "finished_tick": tick,
    }


def _build_simple_step_executed_payload(
    *,
    tick: int,
    task_id: str,
    task_name: str,
    execution_log: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    step_results: List[Dict[str, Any]],
    last_step_result: Any,
    current_step_index: int,
    step_count: int,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "action": "simple_step_executed",
        "tick": tick,
        "task_id": task_id,
        "task_name": task_name,
        "status": "queued",
        "message": "step executed, waiting next tick",
        "final_answer": "",
        "execution_log": execution_log,
        "results": results,
        "step_results": step_results,
        "last_step_result": last_step_result,
        "current_step_index": current_step_index,
        "step_count": step_count,
        "steps_total": step_count,
        "last_run_tick": tick,
    }


def _build_simple_blocked_or_failed_payload(
    *,
    tick: int,
    task_id: str,
    task_name: str,
    status: str,
    message: str,
    normalized_step_result: Dict[str, Any],
    blocked: bool,
    error_type: str,
    execution_log: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    step_results: List[Dict[str, Any]],
    last_step_result: Any,
    current_step_index: int,
    step_count: int,
) -> Dict[str, Any]:
    return {
        "ok": False,
        "action": "simple_step_blocked" if blocked else "simple_step_failed",
        "tick": tick,
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
        "step_count": step_count,
        "steps_total": step_count,
        "last_run_tick": tick,
        "last_failure_tick": tick if not blocked else None,
    }
