import os

from core.agent_loop import AgentLoop
from core.llm_client import LocalLLMClient


class SimpleToolRegistry:
    def __init__(self) -> None:
        self.tools = {
            "file_tool": self._file_tool,
            "command_tool": self._command_tool,
            "web_search": self._web_search,
        }

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self.tools

    def execute_tool(self, tool_name: str, arguments: dict):
        handler = self.tools.get(tool_name)
        if handler is None:
            return {
                "success": False,
                "tool_name": tool_name,
                "result": None,
                "error": f"Unknown tool: {tool_name}",
            }
        return handler(arguments)

    def get_tool_descriptions(self) -> str:
        return """
- file_tool:
  description: Read and write files inside workspace.
  supported actions:
    - write_file(path, content)
    - read_file(path)

- command_tool:
  description: Execute safe shell commands.
  supported actions:
    - run(command)

- web_search:
  description: Search web information.
  supported actions:
    - search(query)
""".strip()

    def _file_tool(self, arguments: dict):
        action = arguments.get("action")
        path = arguments.get("path")
        content = arguments.get("content", "")

        if action == "write_file":
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return {
                "success": True,
                "tool_name": "file_tool",
                "result": {
                    "action": action,
                    "path": path,
                    "bytes_written": len(content.encode("utf-8")),
                },
                "error": None,
            }

        if action == "read_file":
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            return {
                "success": True,
                "tool_name": "file_tool",
                "result": {
                    "action": action,
                    "path": path,
                    "content": text,
                },
                "error": None,
            }

        return {
            "success": False,
            "tool_name": "file_tool",
            "result": None,
            "error": f"Unsupported action: {action}",
        }

    def _command_tool(self, arguments: dict):
        return {
            "success": True,
            "tool_name": "command_tool",
            "result": {
                "note": "Blocked for confirmation in test mode.",
                "arguments": arguments,
            },
            "error": None,
        }

    def _web_search(self, arguments: dict):
        query = arguments.get("query", "")
        return {
            "success": True,
            "tool_name": "web_search",
            "result": {
                "query": query,
                "items": [
                    {"title": "Example Result 1", "url": "https://example.com/1"},
                    {"title": "Example Result 2", "url": "https://example.com/2"},
                ],
            },
            "error": None,
        }


def main() -> None:
    workspace_root = "."

    if os.path.exists("notes.txt"):
        os.remove("notes.txt")
    if os.path.exists("upper.txt"):
        os.remove("upper.txt")

    registry = SimpleToolRegistry()
    llm_client = LocalLLMClient(model_name="zero_general:latest")
    agent = AgentLoop(
        llm_client=llm_client,
        tool_registry=registry,
        max_steps=3,
        workspace_root=workspace_root,
    )

    print("=== CASE 1 ===")
    result_1 = agent.run("幫我建立一個 notes.txt，內容是 hello")
    print(result_1)
    print()

    print("=== CASE 2 ===")
    result_2 = agent.run("請讀取 notes.txt 的內容，然後告訴我裡面寫了什麼")
    print(result_2)
    print()

    print("=== CASE 3 ===")
    result_3 = agent.run("目前工作區裡有哪些檔案？如果 notes.txt 存在，也一起告訴我。")
    print(result_3)
    print()


if __name__ == "__main__":
    main()