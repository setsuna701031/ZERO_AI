from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional


class TaskStepExecutorAdapter:
    """
    Task -> Steps -> StepExecutor

    目標：
    1. 將 task 正規化成 step list
    2. 交給 StepExecutor 逐步執行
    3. 保留 previous_result 傳遞
    4. 回傳結構化結果，讓上層 task runtime / scheduler 可用
    """

    def __init__(
        self,
        step_executor: Any,
        tool_registry: Optional[Any] = None,
        workspace: str = "workspace",
    ) -> None:
        self.step_executor = step_executor
        self.tool_registry = tool_registry
        self.workspace = workspace

    # ============================================================
    # public
    # ============================================================

    def execute_task(
        self,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not isinstance(task, dict):
            return {
                "ok": False,
                "error": "task must be dict",
                "task": task,
                "results": [],
            }

        context = copy.deepcopy(context) if isinstance(context, dict) else {}

        normalized_task = copy.deepcopy(task)
        normalized_task.setdefault("workspace", self._resolve_task_workspace(normalized_task))

        steps = self._task_to_steps(normalized_task)

        if not steps:
            return {
                "ok": False,
                "error": "task produced no executable steps",
                "task": normalized_task,
                "results": [],
            }

        results: List[Dict[str, Any]] = []
        previous_result: Any = None

        for step_index, step in enumerate(steps):
            step_copy = copy.deepcopy(step)
            step_copy.setdefault("step_index", step_index)

            result = self._execute_one_step(
                step=step_copy,
                task=normalized_task,
                context=context,
                previous_result=previous_result,
            )

            if not isinstance(result, dict):
                result = {
                    "ok": False,
                    "error": "step_executor returned non-dict result",
                    "result": result,
                    "step": step_copy,
                }

            result.setdefault("step_index", step_index)
            result.setdefault("step", step_copy)

            results.append(result)
            previous_result = result.get("result", result)

            if not result.get("ok", False):
                return {
                    "ok": False,
                    "task_id": normalized_task.get("id"),
                    "task": normalized_task,
                    "failed_step_index": step_index,
                    "failed_step": step_copy,
                    "results": results,
                    "message": result.get("error", "step execution failed"),
                }

        final_message = self._build_final_message(normalized_task, results)

        return {
            "ok": True,
            "task_id": normalized_task.get("id"),
            "task": normalized_task,
            "steps": steps,
            "results": results,
            "message": final_message,
        }

    # ============================================================
    # conversion
    # ============================================================

    def _task_to_steps(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        優先順序：
        1. task["steps"] 已存在 -> 直接正規化
        2. task["plan"]["steps"] -> 正規化
        3. fallback：根據 title / goal / input 轉最小可用步驟
        """

        # 1) task["steps"]
        raw_steps = task.get("steps")
        if isinstance(raw_steps, list) and raw_steps:
            return [self._normalize_step(step, task=task) for step in raw_steps]

        # 2) task["plan"]["steps"]
        plan = task.get("plan")
        if isinstance(plan, dict):
            plan_steps = plan.get("steps")
            if isinstance(plan_steps, list) and plan_steps:
                return [self._normalize_step(step, task=task) for step in plan_steps]

        # 3) fallback
        fallback_step = self._build_fallback_step(task)
        return [fallback_step] if fallback_step else []

    def _normalize_step(self, step: Any, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        對齊你現在的 StepExecutor：
        - type
        - tool_name
        - tool_input
        """

        if isinstance(step, str):
            return {
                "type": "respond",
                "message": step,
            }

        if not isinstance(step, dict):
            return {
                "type": "respond",
                "message": str(step),
            }

        normalized = copy.deepcopy(step)

        # kind -> type
        if "type" not in normalized and "kind" in normalized:
            normalized["type"] = normalized["kind"]

        # tool -> tool_name
        if "tool_name" not in normalized and "tool" in normalized:
            normalized["tool_name"] = normalized["tool"]

        # input -> tool_input
        if "tool_input" not in normalized and "input" in normalized:
            normalized["tool_input"] = normalized["input"]

        step_type = str(normalized.get("type") or "").strip().lower()

        # 如果是 tool step，補齊欄位
        if step_type in {"tool", "tool_call", "use_tool"}:
            tool_name = normalized.get("tool_name") or normalized.get("tool")
            tool_input = normalized.get("tool_input") or normalized.get("input") or {}

            if not isinstance(tool_input, dict):
                tool_input = {"input": tool_input}

            tool_input = copy.deepcopy(tool_input)

            # 把 task workspace / cwd 塞進去，但不要硬改 path
            tool_input.setdefault("workspace", self._resolve_task_workspace(task))
            tool_input.setdefault("cwd", task.get("cwd") or self._resolve_task_workspace(task))

            normalized["type"] = "tool"
            normalized["tool_name"] = tool_name
            normalized["tool_input"] = tool_input

        return normalized

    def _build_fallback_step(self, task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        當 planner 還沒真的產 steps 時，做最小可用 fallback。
        注意：這只是保底，不是正式 planner。
        """

        title = str(task.get("title") or "").strip()
        goal = str(task.get("goal") or "").strip()
        user_input = str(task.get("input") or task.get("user_input") or "").strip()

        text = title or goal or user_input
        if not text:
            return None

        # 如果 task 已經明確指定 path/content，就優先轉成 write tool step
        path = task.get("path") or task.get("file_path")
        content = task.get("content") or task.get("text")

        if path:
            return {
                "type": "tool",
                "tool_name": "workspace",
                "tool_input": {
                    "action": "write",
                    "path": str(path),
                    "content": "" if content is None else str(content),
                },
            }

        # 否則保底成 respond，避免亂寫檔
        return {
            "type": "respond",
            "message": text,
        }

    # ============================================================
    # execution
    # ============================================================

    def _execute_one_step(
        self,
        step: Dict[str, Any],
        task: Dict[str, Any],
        context: Dict[str, Any],
        previous_result: Any = None,
    ) -> Dict[str, Any]:
        """
        相容不同版本的 StepExecutor 呼叫介面。
        """

        candidates = [
            "execute_one_step",
            "execute_step",
            "run_step",
            "execute",
            "run",
        ]

        for method_name in candidates:
            fn = getattr(self.step_executor, method_name, None)
            if not callable(fn):
                continue

            # 先走你現在 runtime/step_executor.py 常見介面
            try:
                return fn(
                    step=step,
                    task=task,
                    context=context,
                    previous_result=previous_result,
                )
            except TypeError:
                pass

            # 有些版本可能只吃 step / task
            try:
                return fn(
                    step=step,
                    task=task,
                    previous_result=previous_result,
                )
            except TypeError:
                pass

            # 最後保底
            try:
                return fn(step)
            except TypeError:
                continue

        return {
            "ok": False,
            "error": "no callable execution method found on step_executor",
            "step": step,
            "result": None,
        }

    # ============================================================
    # helpers
    # ============================================================

    def _resolve_task_workspace(self, task: Dict[str, Any]) -> str:
        return str(
            task.get("workspace")
            or task.get("cwd")
            or self.workspace
        )

    def _build_final_message(
        self,
        task: Dict[str, Any],
        results: List[Dict[str, Any]],
    ) -> str:
        if not results:
            return "task completed"

        last = results[-1]
        last_result = last.get("result")

        if isinstance(last_result, dict):
            if "final_answer" in last_result:
                return str(last_result["final_answer"])
            if "message" in last_result:
                return str(last_result["message"])
            if "path" in last_result and last.get("ok"):
                return f"task completed: {last_result['path']}"

        return str(task.get("title") or task.get("goal") or "task completed")