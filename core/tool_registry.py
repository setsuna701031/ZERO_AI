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

        # runtime._get_tool() 會看 get_tool / tools / _tools
        # 所以這裡三個都對齊
        self.tools: Dict[str, Any] = {}
        self._tools = self.tools

    # ---------------------------------------------------------
    # register
    # ---------------------------------------------------------

    def register_tool(self, name: str, tool: Any) -> None:
        if not name or tool is None:
            return

        self.tools[name] = tool
        self._tools = self.tools

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

        params = params or {}

        # 先試 execute(args_dict)
        execute = getattr(tool, "execute", None)
        if callable(execute):
            try:
                result = execute({"action": action, **params})
                return {
                    "success": True if not isinstance(result, dict) else bool(result.get("success", True)),
                    "message": "",
                    "data": result,
                }
            except TypeError:
                pass
            except Exception as exc:
                return {
                    "success": False,
                    "message": str(exc),
                    "data": {},
                }

        # 再試 execute(action, params)
        if callable(execute):
            try:
                result = execute(action, params)
                return {
                    "success": True if not isinstance(result, dict) else bool(result.get("success", True)),
                    "message": "",
                    "data": result,
                }
            except Exception as exc:
                return {
                    "success": False,
                    "message": str(exc),
                    "data": {},
                }

        # 再試 run(**params)
        run = getattr(tool, "run", None)
        if callable(run):
            try:
                result = run(**params)
                return {
                    "success": True if not isinstance(result, dict) else bool(result.get("success", True)),
                    "message": "",
                    "data": result,
                }
            except Exception as exc:
                return {
                    "success": False,
                    "message": str(exc),
                    "data": {},
                }

        return {
            "success": False,
            "message": f"tool has no supported execute/run method: {tool_name}",
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