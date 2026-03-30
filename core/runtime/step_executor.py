# core/runtime/step_executor.py

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional


class StepExecutor:
    def __init__(
        self,
        tool_registry=None,
        runtime_store=None,
        reflection_engine=None,
        workspace_root: str = "workspace",
        debug: bool = False,
    ):
        self.tool_registry = tool_registry
        self.runtime_store = runtime_store
        self.reflection_engine = reflection_engine
        self.workspace_root = workspace_root
        self.debug = debug

    # ============================================================
    # Single step
    # ============================================================

    def execute_step(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        previous_result: Any = None,
    ) -> Dict[str, Any]:

        step_type = step.get("type")

        if step_type == "tool":
            return self._execute_tool_step(step, previous_result)

        if step_type == "respond":
            return {
                "ok": True,
                "result": step.get("message"),
                "step": step,
            }

        if step_type == "write_file":
            return self._execute_write_file(step)

        if step_type == "read_file":
            return self._execute_read_file(step)

        return {
            "ok": True,
            "result": "unknown step type",
            "step": step,
        }

    # ============================================================
    # Multi step
    # ============================================================

    def execute_steps(
        self,
        steps: List[Dict[str, Any]],
        task: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:

        results = []
        previous_result = None

        for i, step in enumerate(steps):
            step["step_index"] = i

            result = self.execute_step(
                step=step,
                task=task,
                context=context,
                previous_result=previous_result,
            )

            results.append(result)
            previous_result = result

            if not result.get("ok"):
                return {
                    "ok": False,
                    "failed_step": i,
                    "results": results,
                }

        return {
            "ok": True,
            "results": results,
        }

    # ============================================================
    # Tool step
    # ============================================================

    def _execute_tool_step(self, step, previous_result):
        tool_name = step.get("tool_name")
        tool_input = step.get("tool_input", {})

        if previous_result:
            tool_input["previous_result"] = previous_result

        tool = self.tool_registry.get_tool(tool_name)

        if not tool:
            return {
                "ok": False,
                "error": f"tool not found: {tool_name}",
            }

        result = tool.execute(tool_input)

        return {
            "ok": True,
            "result": result,
            "step": step,
        }

    # ============================================================
    # Write file
    # ============================================================

    def _execute_write_file(self, step):
        import os

        path = step.get("path")
        content = step.get("content", "")

        if not path:
            return {"ok": False, "error": "path missing"}

        full_path = os.path.join(self.workspace_root, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "ok": True,
            "result": {"path": full_path},
            "step": step,
        }

    # ============================================================
    # Read file
    # ============================================================

    def _execute_read_file(self, step):
        import os

        path = step.get("path")

        if not path:
            return {"ok": False, "error": "path missing"}

        full_path = os.path.join(self.workspace_root, path)

        if not os.path.exists(full_path):
            return {"ok": False, "error": "file not found"}

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        return {
            "ok": True,
            "result": {"content": content},
            "step": step,
        }