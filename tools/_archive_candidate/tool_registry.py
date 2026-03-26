from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.base_tool import BaseTool


class ToolRegistry:
    """
    ZERO 工具註冊中心

    作用：
    1. 統一管理所有工具
    2. 提供工具查詢
    3. 提供工具定義列表給 Agent / LLM
    4. 執行指定工具
    """

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """
        註冊單一工具
        """
        if not isinstance(tool, BaseTool):
            raise TypeError("tool must inherit from BaseTool")

        if not tool.name:
            raise ValueError("tool.name cannot be empty")

        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")

        self._tools[tool.name] = tool

    def unregister(self, tool_name: str) -> None:
        """
        移除工具
        """
        if tool_name in self._tools:
            del self._tools[tool_name]

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        return self._tools.get(tool_name)

    def list_tool_names(self) -> List[str]:
        return list(self._tools.keys())

    def list_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        回傳所有工具定義，提供給 Agent / LLM 使用
        """
        return [tool.get_definition() for tool in self._tools.values()]

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        執行工具
        """
        tool = self.get_tool(tool_name)
        if tool is None:
            return {
                "ok": False,
                "error": "tool_not_found",
                "tool_name": tool_name,
                "details": [f"Tool '{tool_name}' is not registered"],
            }

        try:
            return tool.run(arguments)
        except Exception as exc:
            return {
                "ok": False,
                "error": "tool_execution_failed",
                "tool_name": tool_name,
                "details": [str(exc)],
            }

    def debug_dump(self) -> Dict[str, Any]:
        """
        除錯用：查看目前 registry 狀態
        """
        return {
            "tool_count": len(self._tools),
            "tools": self.list_tool_definitions(),
        }