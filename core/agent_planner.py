import re
from core.llm import LLMClient
from core.tool_router import get_available_tools


class AgentPlanner:
    def __init__(self, model: str = "qwen:7b"):
        self.llm = LLMClient(model=model)

    def rule_brain(self, user_input: str):
        text = str(user_input or "").strip()
        lower = text.lower()

        if not text:
            return [{
                "action": "reply",
                "message": "input is required"
            }]

        if (
            "list files" in lower
            or "show files" in lower
            or "列出檔案" in text
            or "列出資料夾" in text
        ):
            return [{
                "action": "tool",
                "tool": "list_files",
                "args": {"path": "."}
            }]

        m = re.match(r"read\s+(.+)", lower)
        if m:
            path = m.group(1).strip()
            return [{
                "action": "tool",
                "tool": "read_file",
                "args": {"path": path}
            }]

        m = re.match(r"讀取\s+(.+)", text)
        if m:
            path = m.group(1).strip()
            return [{
                "action": "tool",
                "tool": "read_file",
                "args": {"path": path}
            }]

        m = re.match(r"run\s+(.+\.py)", lower)
        if m:
            path = m.group(1).strip()
            return [{
                "action": "tool",
                "tool": "run_python",
                "args": {"path": path}
            }]

        m = re.match(r"執行\s+(.+\.py)", text)
        if m:
            path = m.group(1).strip()
            return [{
                "action": "tool",
                "tool": "run_python",
                "args": {"path": path}
            }]

        if "建立並執行" in text or "create and run" in lower:
            match = re.search(r"([\w/\\.-]+\.py)", text)
            if match:
                path = match.group(1)
                return [
                    {
                        "action": "tool",
                        "tool": "write_file",
                        "args": {
                            "path": path,
                            "content": 'print("hello from zero")'
                        }
                    },
                    {
                        "action": "tool",
                        "tool": "run_python",
                        "args": {
                            "path": path
                        }
                    }
                ]

        if (
            "寫一個python程式" in text
            or "寫一支python程式" in text
            or "generate python" in lower
            or "write python" in lower
            or "create python script" in lower
        ):
            match = re.search(r"([\w/\\.-]+\.py)", text)
            filename = match.group(1) if match else "generated.py"

            return [
                {
                    "action": "tool",
                    "tool": "generate_python",
                    "args": {
                        "task": text,
                        "filename": filename,
                        "model": "qwen:7b"
                    }
                },
                {
                    "action": "tool",
                    "tool": "write_file",
                    "args": {
                        "path": filename,
                        "__from_previous__": "generate_python.code"
                    }
                },
                {
                    "action": "tool",
                    "tool": "run_python",
                    "args": {
                        "path": filename
                    }
                }
            ]

        return None

    def build_prompt(self, user_input: str):
        tools = get_available_tools()
        tool_text = "\n".join([f"- {t}" for t in tools])

        return f"""
You are ZERO agent planner.

Available tools:
{tool_text}

User request:
{user_input}

Output JSON only.

Valid formats:

Reply:
{{
  "action":"reply",
  "message":"I cannot determine the task"
}}

Single step:
{{
  "action":"tool",
  "tool":"list_files",
  "args":{{"path":"."}}
}}

Multi step:
[
  {{
    "action":"tool",
    "tool":"generate_python",
    "args":{{"task":"write a hello world script","filename":"test/hello.py","model":"qwen:7b"}}
  }},
  {{
    "action":"tool",
    "tool":"write_file",
    "args":{{"path":"test/hello.py","content":"print(1)"}}
  }},
  {{
    "action":"tool",
    "tool":"run_python",
    "args":{{"path":"test/hello.py"}}
  }}
]
""".strip()

    def llm_brain(self, user_input: str):
        prompt = self.build_prompt(user_input)
        result = self.llm.generate_json(prompt)

        if not result["success"]:
            return [{
                "action": "reply",
                "message": result["raw"]
            }]

        data = result["data"]

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            return [data]

        return [{
            "action": "reply",
            "message": "planner returned invalid format"
        }]

    def build_plan(self, user_input: str):
        fast = self.rule_brain(user_input)
        if fast is not None:
            return fast
        return self.llm_brain(user_input)