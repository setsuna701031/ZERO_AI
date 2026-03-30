# ZERO core tools package

from __future__ import annotations


def _safe_import(name: str):
    try:
        module = __import__(f"{__name__}.{name}", fromlist=["*"])
        return module
    except Exception:
        return None


_command_tool_module = _safe_import("command_tool")
_workspace_tool_module = _safe_import("workspace_tool")
_file_tool_module = _safe_import("file_tool")
_web_search_tool_module = _safe_import("web_search_tool")

CommandTool = getattr(_command_tool_module, "CommandTool", None)
WorkspaceTool = getattr(_workspace_tool_module, "WorkspaceTool", None)
FileTool = getattr(_file_tool_module, "FileTool", None)
WebSearchTool = getattr(_web_search_tool_module, "WebSearchTool", None)

__all__ = [
    "CommandTool",
    "WorkspaceTool",
    "FileTool",
    "WebSearchTool",
]