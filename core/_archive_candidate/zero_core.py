from core.router import Router
from core.llm import LocalLLM
from memory.memory_store import MemoryStore
from tools.registry import ToolRegistry


class ZeroCore:

    def __init__(self):

        print("ZeroCore initialized")

        self.router = Router()
        self.llm = LocalLLM()
        self.memory = MemoryStore()
        self.registry = ToolRegistry()

    def handle(self, text):

        task = self.router.route(text)

        task_type = task.get("type")

        if task_type == "help":
            return "commands: help, tools, memory, list files, read file <path>, run python <path>, write file <path>|||<content>, echo <text>, run example, ask <question>"

        if task_type == "tools":
            return ", ".join(self.registry.list_tools())

        if task_type == "memory":
            return self.memory.read_all()

        if task_type == "ask":
            prompt = task.get("prompt", "")
            result = self.llm.generate(prompt)
            self.memory.save(f"USER: {text}")
            self.memory.save(f"ZERO: {result}")
            return result

        if task_type == "tool":
            tool_name = task.get("tool")
            args = task.get("args", {})

            tool = self.registry.get(tool_name)

            if tool is None:
                return f"tool not found: {tool_name}"

            try:
                result = tool(**args)
            except TypeError as e:
                return f"tool argument error: {str(e)}"
            except Exception as e:
                return f"tool execution error: {str(e)}"

            self.memory.save(f"USER: {text}")
            self.memory.save(f"ZERO: {result}")
            return result

        if task_type == "chat":
            result = f"chat: {task.get('text', '')}"
            self.memory.save(f"USER: {text}")
            self.memory.save(f"ZERO: {result}")
            return result

        return "unknown task"