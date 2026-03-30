from __future__ import annotations

from typing import Any, Dict, Optional


try:
    from core.tools.web_search_tool import WebSearchTool
except Exception:
    WebSearchTool = None  # type: ignore


try:
    from core.tools.workspace_tool import WorkspaceTool
except Exception:
    WorkspaceTool = None  # type: ignore


try:
    from core.tools.file_tool import FileTool
except Exception:
    FileTool = None  # type: ignore


try:
    from core.tools.command_tool import CommandTool
except Exception:
    CommandTool = None  # type: ignore


class ToolRegistry:
    """
    統一工具註冊中心

    這版重點：
    1. 真的註冊 class-based tools
    2. 提供 step_executor 會用到的 get_tool / get / resolve / find_tool
    3. 保留 alias，讓 web_search / search_web / websearch / search 都能對上
    """

    def __init__(self, workspace_dir: str = "workspace") -> None:
        self.workspace_dir = workspace_dir
        self.tools: Dict[str, Any] = {}
        self._register_default_tools()

    # =========================================================
    # public api
    # =========================================================

    def register(self, name: str, tool: Any) -> None:
        key = str(name or "").strip().lower()
        if not key:
            raise ValueError("tool name cannot be empty")
        self.tools[key] = tool

    def has_tool(self, name: str) -> bool:
        key = str(name or "").strip().lower()
        return key in self.tools

    def get_tool(self, name: str) -> Optional[Any]:
        key = str(name or "").strip().lower()
        return self.tools.get(key)

    def get(self, name: str) -> Optional[Any]:
        return self.get_tool(name)

    def resolve(self, name: str) -> Optional[Any]:
        return self.get_tool(name)

    def find_tool(self, name: str) -> Optional[Any]:
        return self.get_tool(name)

    def list_tools(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "count": len(self.tools),
            "tools": sorted(self.tools.keys()),
        }

    # =========================================================
    # default registration
    # =========================================================

    def _register_default_tools(self) -> None:
        web_search_tool = self._safe_build_web_search_tool()
        if web_search_tool is not None:
            self.register("web_search", web_search_tool)
            self.register("search_web", web_search_tool)
            self.register("websearch", web_search_tool)
            self.register("search", web_search_tool)

        workspace_tool = self._safe_build_workspace_tool()
        if workspace_tool is not None:
            self.register("workspace", workspace_tool)
            self.register("workspace_tool", workspace_tool)

        file_tool = self._safe_build_file_tool()
        if file_tool is not None:
            self.register("file", file_tool)
            self.register("file_tool", file_tool)

        command_tool = self._safe_build_command_tool()
        if command_tool is not None:
            self.register("command", command_tool)
            self.register("command_tool", command_tool)

    # =========================================================
    # builders
    # =========================================================

    def _safe_build_web_search_tool(self) -> Optional[Any]:
        if WebSearchTool is None:
            return None

        for kwargs in (
            {},
            {"workspace_dir": self.workspace_dir},
            {"workspace_root": self.workspace_dir},
        ):
            try:
                return WebSearchTool(**kwargs)
            except TypeError:
                continue
            except Exception:
                return None

        try:
            return WebSearchTool()
        except Exception:
            return None

    def _safe_build_workspace_tool(self) -> Optional[Any]:
        if WorkspaceTool is None:
            return None

        for kwargs in (
            {"workspace_root": self.workspace_dir},
            {"workspace_root": self.workspace_dir},
        ):
            try:
                return WorkspaceTool(**kwargs)
            except TypeError:
                continue
            except Exception:
                return None

        try:
            return WorkspaceTool(self.workspace_dir)
        except Exception:
            return None

    def _safe_build_file_tool(self) -> Optional[Any]:
        if FileTool is None:
            return None

        for kwargs in (
            {},
            {"workspace_dir": self.workspace_dir},
            {"workspace_root": self.workspace_dir},
        ):
            try:
                return FileTool(**kwargs)
            except TypeError:
                continue
            except Exception:
                return None

        try:
            return FileTool()
        except Exception:
            return None

    def _safe_build_command_tool(self) -> Optional[Any]:
        if CommandTool is None:
            return None

        for kwargs in (
            {},
            {"workspace_dir": self.workspace_dir},
            {"workspace_root": self.workspace_dir},
        ):
            try:
                return CommandTool(**kwargs)
            except TypeError:
                continue
            except Exception:
                return None

        try:
            return CommandTool()
        except Exception:
            return None