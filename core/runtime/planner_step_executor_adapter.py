from __future__ import annotations

import copy
import time
from typing import Any, Dict, List


SCHEMA = "zero.aer.planner_step_executor_adapter.v1"
TOOL_BRIDGE_SCHEMA = "zero.aer.planner_step_executor_adapter.tool_bridge.v1"


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
    - This adapter does not call ToolRegistry directly.
    - It only converts the current planner step/group into a StepExecutor call.

    v8.2.8 runtime fix:
    - Planner tool-call steps are normalized into StepExecutor's canonical
      tool-step shape.
    - The important compatibility field is `tool_input`.  The existing
      StepExecutor/Planner examples use `tool_input` for tool steps, while the
      lower-level ToolCallExecutor also understands `args` / `input`.  This
      adapter now supplies all three fields so the StepExecutor tool handler,
      ToolCallExecutor, and ToolRegistry can share the same payload.
    """

    def __init__(self, step_executor: Any) -> None:
        self.step_executor = step_executor
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, group: List[str], group_index: int, session: Any) -> Dict[str, Any]:
        task = getattr(session, "task", {})
        if not isinstance(task, dict):
            task = {}

        raw_step = self._select_step(task=task, group=group, group_index=group_index)
        step = self._normalize_planner_step_for_step_executor(raw_step)
        context = self._build_context(task=task, group=group, group_index=group_index, session=session)

        call_record = {
            "schema": SCHEMA,
            "group_index": group_index,
            "group": copy.deepcopy(group),
            "raw_step": copy.deepcopy(raw_step),
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
        if isinstance(result, dict):
            result.setdefault("step_type", _clean_text(step.get("type")).lower() or "unknown")
            result.setdefault("step", copy.deepcopy(step))

        ok = bool(result.get("ok")) if isinstance(result, dict) else False
        return {
            "ok": ok,
            "schema": SCHEMA,
            "status": "finished" if ok else "failed",
            "message": "planner step executed through StepExecutor adapter" if ok else "planner step execution failed",
            "group_index": group_index,
            "group": copy.deepcopy(group),
            "raw_step": copy.deepcopy(raw_step),
            "step": copy.deepcopy(step),
            "step_executor_result": copy.deepcopy(result),
            "adapter_call": call_record,
            "tool_bridge": copy.deepcopy(step.get("planner_tool_bridge")) if isinstance(step.get("planner_tool_bridge"), dict) else {},
            "boundary": {
                "adapter_only": True,
                "step_executor_remains_execution_endpoint": True,
                "execution_gateway_not_called_directly": True,
                "tool_registry_not_called_directly": True,
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

    def _normalize_planner_step_for_step_executor(self, step: Dict[str, Any]) -> Dict[str, Any]:
        normalized = copy.deepcopy(step) if isinstance(step, dict) else {}
        step_type = _clean_text(normalized.get("type")).lower()

        tool_name = self._extract_tool_name(normalized)
        tool_args = self._extract_tool_args(normalized)
        self._normalize_tool_path_contract(tool_args)

        is_tool_shape = bool(tool_name) and (
            step_type in {"tool", "tool_call", "tool_request", "call_tool", "l4_tool"}
            or bool(normalized.get("tool_call"))
            or bool(normalized.get("use_tool"))
            or bool(normalized.get("planner_tool_call"))
        )

        if is_tool_shape:
            original_type = step_type or "tool"
            normalized["type"] = "tool"
            normalized["tool_name"] = tool_name
            normalized["tool"] = tool_name

            # Compatibility closure:
            # - StepExecutor planner examples use tool_input.
            # - ToolCallExecutor normalize_tool_call understands args/input.
            # - ToolRegistry receives ToolRequest.input from the tool handler.
            normalized["tool_input"] = copy.deepcopy(tool_args)
            normalized["args"] = copy.deepcopy(tool_args)
            normalized["input"] = copy.deepcopy(tool_args)

            normalized["planner_step_executor_adapter"] = True
            normalized["planner_tool_bridge"] = {
                "schema": TOOL_BRIDGE_SCHEMA,
                "enabled": True,
                "original_type": original_type,
                "tool_name": tool_name,
                "args_keys": sorted(str(key) for key in tool_args.keys()),
                "step_executor_tool_handler": True,
                "tool_registry_called_by_step_executor": True,
                "tool_input_compatibility": True,
            }
            return normalized

        normalized["planner_step_executor_adapter"] = True
        return normalized

    @staticmethod
    def _normalize_tool_path_contract(tool_args: Dict[str, Any]) -> None:
        """Preserve planner target_path while supplying the file-tool path key."""
        target_path = _clean_text(tool_args.get("target_path"))
        path = _clean_text(tool_args.get("path"))
        if target_path and not path:
            tool_args["path"] = target_path

    def _extract_tool_name(self, step: Dict[str, Any]) -> str:
        for key in ("tool_name", "tool", "name"):
            value = _clean_text(step.get(key))
            if value:
                return value

        tool_call = step.get("tool_call")
        if isinstance(tool_call, dict):
            for key in ("tool_name", "tool", "name"):
                value = _clean_text(tool_call.get(key))
                if value:
                    return value

        request = step.get("request")
        if isinstance(request, dict):
            for key in ("tool_name", "tool", "name"):
                value = _clean_text(request.get(key))
                if value:
                    return value

        return ""

    def _extract_tool_args(self, step: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("tool_input", "args", "input", "arguments", "params"):
            value = step.get(key)
            if isinstance(value, dict):
                return copy.deepcopy(value)

        tool_call = step.get("tool_call")
        if isinstance(tool_call, dict):
            for key in ("tool_input", "args", "input", "arguments", "params"):
                value = tool_call.get(key)
                if isinstance(value, dict):
                    return copy.deepcopy(value)

        request = step.get("request")
        if isinstance(request, dict):
            for key in ("tool_input", "args", "input", "arguments", "params"):
                value = request.get(key)
                if isinstance(value, dict):
                    return copy.deepcopy(value)

        args: Dict[str, Any] = {}
        for key in (
            "path",
            "target_path",
            "content",
            "allow_overwrite",
            "create_if_missing",
            "ensure_trailing_newline",
            "recursive",
        ):
            if key in step:
                args[key] = copy.deepcopy(step.get(key))
        return args

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
    "TOOL_BRIDGE_SCHEMA",
    "PlannerStepExecutorAdapter",
]
