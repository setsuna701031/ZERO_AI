from __future__ import annotations

import copy
import time
from typing import Any, Dict, List


SCHEMA = "zero.aer.planner_step_executor_adapter.v1"


def _now() -> float:
    return time.time()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


class PlannerStepExecutorAdapter:
    """Adapt planner-runtime groups into StepExecutor calls.

    Executor contract expected by LongEngineeringRuntime:

        executor(group: list[str], group_index: int, session: LongEngineeringRuntime) -> dict

    Boundary:
    - This adapter does not plan.
    - This adapter does not own sessions/checkpoints/recovery.
    - This adapter does not call ExecutionGateway directly.
    - It only converts the current planner step/group into a StepExecutor call.
    """

    def __init__(self, step_executor: Any) -> None:
        self.step_executor = step_executor
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, group: List[str], group_index: int, session: Any) -> Dict[str, Any]:
        task = getattr(session, "task", {})
        if not isinstance(task, dict):
            task = {}

        step = self._select_step(task=task, group=group, group_index=group_index)
        context = self._build_context(task=task, group=group, group_index=group_index, session=session)

        call_record = {
            "schema": SCHEMA,
            "group_index": group_index,
            "group": copy.deepcopy(group),
            "step": copy.deepcopy(step),
            "task_id": task.get("id") or task.get("task_id") or getattr(session, "task_id", ""),
            "session_id": getattr(session, "session_id", ""),
            "created_at": _now(),
        }
        self.calls.append(call_record)

        if self.step_executor is None:
            return {
                "ok": False,
                "schema": SCHEMA,
                "status": "step_executor_missing",
                "message": "PlannerStepExecutorAdapter has no StepExecutor",
                "group_index": group_index,
                "group": copy.deepcopy(group),
                "step": copy.deepcopy(step),
                "adapter_call": call_record,
            }

        result = self._call_step_executor(
            step=step,
            task=task,
            context=context,
            group_index=group_index,
        )

        ok = bool(result.get("ok")) if isinstance(result, dict) else False
        return {
            "ok": ok,
            "schema": SCHEMA,
            "status": "finished" if ok else "failed",
            "message": "planner step executed through StepExecutor adapter" if ok else "planner step execution failed",
            "group_index": group_index,
            "group": copy.deepcopy(group),
            "step": copy.deepcopy(step),
            "step_executor_result": copy.deepcopy(result),
            "adapter_call": call_record,
            "boundary": {
                "adapter_only": True,
                "step_executor_remains_execution_endpoint": True,
                "execution_gateway_not_called_directly": True,
                "planner_not_executing": True,
            },
        }

    def _select_step(self, *, task: Dict[str, Any], group: List[str], group_index: int) -> Dict[str, Any]:
        steps = task.get("planner_steps")
        if not isinstance(steps, list):
            planner_result = task.get("planner_result")
            if isinstance(planner_result, dict) and isinstance(planner_result.get("steps"), list):
                steps = planner_result.get("steps")
            elif isinstance(task.get("steps"), list):
                steps = task.get("steps")
            else:
                steps = []

        if 0 <= group_index < len(steps) and isinstance(steps[group_index], dict):
            step = copy.deepcopy(steps[group_index])
        else:
            description = "; ".join(_clean_text(item) for item in _safe_list(group) if _clean_text(item))
            step = {
                "type": "planner_runtime_group",
                "description": description or f"planner runtime group {group_index + 1}",
            }

        if not _clean_text(step.get("type")):
            step["type"] = "planner_runtime_group"

        step["planner_runtime_group"] = copy.deepcopy(group)
        step["planner_runtime_group_index"] = int(group_index)
        step["planner_step_executor_adapter"] = True
        return step

    def _build_context(self, *, task: Dict[str, Any], group: List[str], group_index: int, session: Any) -> Dict[str, Any]:
        return {
            "source": "PlannerStepExecutorAdapter",
            "schema": SCHEMA,
            "task_id": task.get("id") or task.get("task_id") or getattr(session, "task_id", ""),
            "session_id": getattr(session, "session_id", ""),
            "goal": task.get("goal") or getattr(session, "goal", ""),
            "group": copy.deepcopy(group),
            "group_index": int(group_index),
            "planner_step_executor_adapter": True,
        }

    def _call_step_executor(
        self,
        *,
        step: Dict[str, Any],
        task: Dict[str, Any],
        context: Dict[str, Any],
        group_index: int,
    ) -> Dict[str, Any]:
        for method_name in ("execute", "execute_step"):
            method = getattr(self.step_executor, method_name, None)
            if not callable(method):
                continue

            try:
                result = method(
                    step=copy.deepcopy(step),
                    task=copy.deepcopy(task),
                    context=copy.deepcopy(context),
                    previous_result=None,
                    step_index=group_index + 1,
                    step_count=None,
                )
                return result if isinstance(result, dict) else {
                    "ok": False,
                    "status": "invalid_step_executor_result",
                    "message": "StepExecutor returned non-dict result",
                    "raw_result": copy.deepcopy(result),
                }
            except TypeError:
                try:
                    result = method(copy.deepcopy(step), copy.deepcopy(task), copy.deepcopy(context))
                    return result if isinstance(result, dict) else {
                        "ok": False,
                        "status": "invalid_step_executor_result",
                        "message": "StepExecutor returned non-dict result",
                        "raw_result": copy.deepcopy(result),
                    }
                except Exception as exc:
                    return {
                        "ok": False,
                        "status": "step_executor_exception",
                        "message": f"{type(exc).__name__}: {exc}",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
            except Exception as exc:
                return {
                    "ok": False,
                    "status": "step_executor_exception",
                    "message": f"{type(exc).__name__}: {exc}",
                    "error": f"{type(exc).__name__}: {exc}",
                }

        return {
            "ok": False,
            "status": "step_executor_method_missing",
            "message": "StepExecutor has no execute/execute_step method",
        }


__all__ = [
    "SCHEMA",
    "PlannerStepExecutorAdapter",
]
