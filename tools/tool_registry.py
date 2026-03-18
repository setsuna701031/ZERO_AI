from tools.terminal_tool import TerminalTool
from tools.project_tool import ProjectTool
from tools.web_search_tool import WebSearchTool
from tools.search_code_tool import SearchCodeTool
from tools.read_file_tool import ReadFileTool
from tools.write_file_tool import WriteFileTool


class ToolRegistry:
    def __init__(self):
        self.tools = {
            "terminal": TerminalTool(),
            "project": ProjectTool(),
            "web_search": WebSearchTool(),
            "search_code": SearchCodeTool(),
            "read_file": ReadFileTool(),
            "write_file": WriteFileTool()
        }

    def execute(self, tool_name: str, action: str, **kwargs):
        tool = self.tools.get(tool_name)

        if not tool:
            return {
                "ok": False,
                "error": f"Tool not found: {tool_name}"
            }

        method = getattr(tool, action, None)

        if not method:
            return {
                "ok": False,
                "error": f"Action not found: {action}"
            }

        try:
            return method(**kwargs)
        except Exception as e:
            return {
                "ok": False,
                "error": f"{type(e).__name__}: {e}"
            }