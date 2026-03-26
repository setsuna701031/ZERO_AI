from __future__ import annotations

from typing import Any, Dict, Optional


class ToolRegistry:
    """
    ZERO Tool Registry

    作用：
    1. 註冊工具
    2. 取得工具
    3. 呼叫工具 execute()
    """

    def __init__(
        self,
        workspace_root: Optional[str] = None,
        project_root: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self.workspace_root = workspace_root
        self.project_root = project_root
        self.tools: Dict[str, Any] = {}

    # ---------------------------------------------------------
    # register
    # ---------------------------------------------------------

    def register_tool(self, name: str, tool: Any) -> None:
        if not name or tool is None:
            return

        self.tools[name] = tool

    # 相容舊名稱
    def register(self, name: str, tool: Any) -> None:
        self.register_tool(name, tool)

    def add_tool(self, name: str, tool: Any) -> None:
        self.register_tool(name, tool)

    def add(self, name: str, tool: Any) -> None:
        self.register_tool(name, tool)

    # ---------------------------------------------------------
    # get tool
    # ---------------------------------------------------------

    def get_tool(self, name: str) -> Optional[Any]:
        return self.tools.get(name)

    def get(self, name: str) -> Optional[Any]:
        return self.get_tool(name)

    # ---------------------------------------------------------
    # list tools
    # ---------------------------------------------------------

    def list_tools(self) -> Dict[str, Any]:
        return self.tools

    # ---------------------------------------------------------
    # execute tool
    # ---------------------------------------------------------

    def execute_tool(
        self,
        tool_name: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        tool = self.get_tool(tool_name)

        if tool is None:
            return {
                "success": False,
                "message": f"tool not found: {tool_name}",
                "data": {},
            }

        if not hasattr(tool, "execute"):
            return {
                "success": False,
                "message": f"tool has no execute(): {tool_name}",
                "data": {},
            }

        try:
            return tool.execute(action, params or {})
        except Exception as exc:
            return {
                "success": False,
                "message": str(exc),
                "data": {},
            }

    # ---------------------------------------------------------
    # debug info
    # ---------------------------------------------------------

    def debug_info(self) -> Dict[str, Any]:
        return {
            "workspace_root": self.workspace_root,
            "project_root": self.project_root,
            "tools": list(self.tools.keys()),
        }