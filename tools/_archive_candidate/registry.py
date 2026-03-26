from tools.echo_tool import echo_tool
from tools.example_tool import example_tool
from tools.list_files_tool import list_files_tool
from tools.read_file_tool import read_file_tool
from tools.run_python_tool import run_python_tool
from tools.write_file_tool import write_file_tool
from tools.project_context_tool import project_context_tool


class ToolRegistry:

    def __init__(self):

        self.tools = {
            "echo": echo_tool,
            "example": example_tool,
            "list_files": list_files_tool,
            "read_file": read_file_tool,
            "run_python": run_python_tool,
            "write_file": write_file_tool,
            "project_context": project_context_tool
        }

    def get(self, name):
        return self.tools.get(name)

    def list_tools(self):
        return list(self.tools.keys())