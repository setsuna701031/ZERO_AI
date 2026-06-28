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
