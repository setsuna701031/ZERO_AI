from __future__ import annotations
from typing import Any, Dict, List


class Executor:
    """
    Execute plan steps using ToolRegistry
    """

    def __init__(self, tool_registry: Any):
        self.tool_registry = tool_registry

    def execute_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        steps: List[Dict[str, Any]] = plan.get("steps", [])
        results = []

        for step in steps:
            tool_name = step.get("tool")
            args = step.get("args", {})

            tool = self._get_tool(tool_name)
            if tool is None:
                results.append({
                    "ok": False,
                    "error": f"Tool not found: {tool_name}"
                })
                continue

            try:
                result = tool.execute(args)
                results.append(result)
            except Exception as e:
                results.append({
                    "ok": False,
                    "error": str(e)
                })

        return {
            "ok": True,
            "results": results
        }

    def _get_tool(self, name: str):
        if hasattr(self.tool_registry, "get_tool"):
            return self.tool_registry.get_tool(name)

        if hasattr(self.tool_registry, "tools"):
            return self.tool_registry.tools.get(name)

        return Nonefrom __future__ import annotations
from typing import Any, Dict, List


class Executor:
    """
    Execute plan steps using ToolRegistry
    """

    def __init__(self, tool_registry: Any):
        self.tool_registry = tool_registry

    def execute_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        steps: List[Dict[str, Any]] = plan.get("steps", [])
        results = []

        for step in steps:
            tool_name = step.get("tool")
            args = step.get("args", {})

            tool = self._get_tool(tool_name)
            if tool is None:
                results.append({
                    "ok": False,
                    "error": f"Tool not found: {tool_name}"
                })
                continue

            try:
                result = tool.execute(args)
                results.append(result)
            except Exception as e:
                results.append({
                    "ok": False,
                    "error": str(e)
                })

        return {
            "ok": True,
            "results": results
        }

    def _get_tool(self, name: str):
        if hasattr(self.tool_registry, "get_tool"):
            return self.tool_registry.get_tool(name)

        if hasattr(self.tool_registry, "tools"):
            return self.tool_registry.tools.get(name)

        return None