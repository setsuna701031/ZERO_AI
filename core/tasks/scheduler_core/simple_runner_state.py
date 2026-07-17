from __future__ import annotations

import copy

from typing import Any, Dict, List, Tuple


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

