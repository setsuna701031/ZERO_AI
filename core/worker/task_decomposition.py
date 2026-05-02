from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.worker.worker_contracts import (
    ParentTask,
    create_parent_task,
    ensure_parent_task_contract,
    ensure_worker_task_contract,
)
from core.worker.worker_runtime import WorkerRuntime


def create_manual_parent_task(
    *,
    task_id: str,
    objective: str,
    input_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    parent = create_parent_task(
        task_id=task_id,
        objective=objective,
        input_context=input_context,
        decomposition_mode="manual",
    )
    return parent.to_dict()


def decompose_parent_task_manual(
    *,
    parent_task: ParentTask | Dict[str, Any],
    worker_specs: List[Dict[str, Any]],
    runtime: WorkerRuntime,
) -> List[Dict[str, Any]]:
    parent_payload = _coerce_parent_task(parent_task)
    if not isinstance(worker_specs, list) or not 2 <= len(worker_specs) <= 3:
        raise ValueError("manual decomposition requires 2 to 3 worker specs")

    worker_tasks: List[Dict[str, Any]] = []
    for index, spec in enumerate(worker_specs, start=1):
        if not isinstance(spec, dict):
            raise ValueError(f"worker spec {index} must be a dict")

        task_id = str(spec.get("task_id") or f"{parent_payload['task_id']}_worker_{index}").strip()
        objective = str(spec.get("objective") or "").strip()
        role = str(spec.get("role") or "worker").strip()
        input_context = spec.get("input_context")
        if not isinstance(input_context, dict):
            input_context = {}

        task = runtime.create_task(
            task_id=task_id,
            parent_task_id=parent_payload["task_id"],
            role=role,
            objective=objective,
            input_context={
                "parent_objective": parent_payload["objective"],
                "parent_input_context": copy.deepcopy(parent_payload["input_context"]),
                **copy.deepcopy(input_context),
            },
        )
        ensure_worker_task_contract(task)
        worker_tasks.append(task)

    return worker_tasks


def run_manual_decomposition(
    *,
    parent_task: ParentTask | Dict[str, Any],
    worker_specs: List[Dict[str, Any]],
    runtime: WorkerRuntime,
) -> Dict[str, Any]:
    worker_tasks = decompose_parent_task_manual(
        parent_task=parent_task,
        worker_specs=worker_specs,
        runtime=runtime,
    )

    results: List[Dict[str, Any]] = []
    snapshot: Dict[str, Any] = runtime.snapshot_state()
    for worker_task in worker_tasks:
        runner_result = runtime.run_task(worker_task)
        worker_result = runtime.collect_result(worker_task, runner_result)
        results.append(worker_result)
        snapshot = runtime.merge_result(worker_result)

    return {
        "parent_task": _coerce_parent_task(parent_task),
        "worker_tasks": worker_tasks,
        "worker_results": results,
        "snapshot": snapshot,
    }


def _coerce_parent_task(parent_task: ParentTask | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(parent_task, ParentTask):
        payload = parent_task.to_dict()
    else:
        payload = copy.deepcopy(parent_task)
    return ensure_parent_task_contract(payload)
