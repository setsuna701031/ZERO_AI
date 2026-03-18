from typing import Any, Dict, List, Optional

from tools.web_search_tool import WebSearchTool


class ToolRegistry:
    """
    ZERO 工具註冊中心

    作用：
    1. 集中管理所有工具
    2. 提供工具查詢
    3. 提供工具執行入口
    4. 讓 Router / Agent Loop 可以統一呼叫工具
    """

    def __init__(self) -> None:
        self.tools: Dict[str, Any] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """
        註冊預設工具
        目前先放 web_search
        """
        web_search_tool = WebSearchTool()
        self.register_tool(web_search_tool)

    def register_tool(self, tool: Any) -> None:
        """
        註冊單一工具
        工具必須至少有:
        - name
        - execute(params)
        """
        if not hasattr(tool, "name"):
            raise ValueError("Tool must have a 'name' attribute")

        if not hasattr(tool, "execute"):
            raise ValueError("Tool must have an 'execute' method")

        tool_name = str(tool.name).strip()
        if not tool_name:
            raise ValueError("Tool name cannot be empty")

        self.tools[tool_name] = tool

    def unregister_tool(self, tool_name: str) -> bool:
        """
        移除工具
        """
        tool_name = (tool_name or "").strip()
        if tool_name in self.tools:
            del self.tools[tool_name]
            return True
        return False

    def get_tool(self, tool_name: str) -> Optional[Any]:
        """
        取得工具物件
        """
        return self.tools.get((tool_name or "").strip())

    def has_tool(self, tool_name: str) -> bool:
        """
        檢查工具是否存在
        """
        return (tool_name or "").strip() in self.tools

    def list_tool_names(self) -> List[str]:
        """
        列出所有工具名稱
        """
        return list(self.tools.keys())

    def list_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        列出所有工具定義
        若工具有 get_tool_definition() 就優先使用
        """
        definitions: List[Dict[str, Any]] = []

        for tool in self.tools.values():
            if hasattr(tool, "get_tool_definition"):
                try:
                    definitions.append(tool.get_tool_definition())
                    continue
                except Exception as e:
                    definitions.append(
                        {
                            "name": getattr(tool, "name", "unknown"),
                            "description": f"Failed to load tool definition: {str(e)}",
                        }
                    )
            else:
                definitions.append(
                    {
                        "name": getattr(tool, "name", "unknown"),
                        "description": getattr(tool, "description", ""),
                    }
                )

        return definitions

    def execute_tool(
        self,
        tool_name: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        統一工具執行入口
        """
        params = params or {}
        tool_name = (tool_name or "").strip()

        if not tool_name:
            return {
                "success": False,
                "tool_name": tool_name,
                "error": "Tool name is required",
                "results": [],
            }

        tool = self.get_tool(tool_name)
        if tool is None:
            return {
                "success": False,
                "tool_name": tool_name,
                "error": f"Tool not found: {tool_name}",
                "results": [],
            }

        try:
            result = tool.execute(params)

            if not isinstance(result, dict):
                return {
                    "success": False,
                    "tool_name": tool_name,
                    "error": "Tool execute() must return a dict",
                    "results": [],
                }

            if "tool_name" not in result:
                result["tool_name"] = tool_name

            if "success" not in result:
                result["success"] = True

            return result

        except Exception as e:
            return {
                "success": False,
                "tool_name": tool_name,
                "error": f"Tool execution failed: {str(e)}",
                "results": [],
            }


if __name__ == "__main__":
    registry = ToolRegistry()

    print("=" * 80)
    print("REGISTERED TOOLS")
    print(registry.list_tool_names())

    print("=" * 80)
    print("TOOL DEFINITIONS")
    for definition in registry.list_tool_definitions():
        print(definition)

    print("=" * 80)
    print("EXECUTE web_search")
    result = registry.execute_tool(
        "web_search",
        {
            "query": "Python requests 教學",
            "max_results": 3,
            "category": "general",
        },
    )
    print(result)

    print("=" * 80)
    print("EXECUTE unknown_tool")
    result = registry.execute_tool(
        "unknown_tool",
        {
            "query": "test",
        },
    )
    print(result)