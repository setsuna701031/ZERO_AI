from tools.list_files import ListFilesTool
from tools.read_file import ReadFileTool
from tools.search_files import SearchFilesTool
from tools.search_code import SearchCodeTool
from tools.write_file import WriteFileTool
from tools.run_python import RunPythonTool
from tools.analyze_project import AnalyzeProjectTool
from tools.summarize_project import SummarizeProjectTool
from tools.inspect_project import InspectProjectTool
from tools.fix_code_context import FixCodeContextTool
from tools.parse_error import ParseErrorTool
from tools.apply_patch import ApplyPatchTool
from tools.debug_python import DebugPythonTool
from tools.run_shell import RunShellTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, object] = {}

    def register(self, tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str):
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ListFilesTool())
    registry.register(ReadFileTool())
    registry.register(SearchFilesTool())
    registry.register(SearchCodeTool())
    registry.register(WriteFileTool())
    registry.register(RunPythonTool())
    registry.register(AnalyzeProjectTool())
    registry.register(SummarizeProjectTool())
    registry.register(InspectProjectTool())
    registry.register(FixCodeContextTool())
    registry.register(ParseErrorTool())
    registry.register(ApplyPatchTool())
    registry.register(DebugPythonTool())
    registry.register(RunShellTool())
    return registry