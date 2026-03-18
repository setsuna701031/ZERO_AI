import json

from core.agent_planner import AgentPlanner
from core.llm import LLMClient
from core.tool_router import run_tool


class ProjectAgent:
    def __init__(
        self,
        model: str = "qwen:7b",
        max_steps: int = 20,
        max_fix_attempts: int = 3
    ):
        self.model = model
        self.max_steps = max_steps
        self.max_fix_attempts = max_fix_attempts
        self.planner = AgentPlanner(model=model)
        self.llm = LLMClient(model=model)

    def cleanup_code_block(self, text: str) -> str:
        return self.llm.extract_python_code(text)

    def build_final_answer(self, results: list) -> str:
        if not results:
            return "No steps were executed."

        last = results[-1].get("result", {})
        tool_name = str(last.get("tool", "")).strip()
        success = bool(last.get("success", False))
        data = last.get("data", {})

        if not success:
            if isinstance(data, dict):
                return str(data.get("message", "Tool execution failed."))
            return "Tool execution failed."

        if tool_name == "list_files":
            path = data.get("path", ".")
            items = data.get("items", [])

            if not items:
                return f"No items found in folder: {path}"

            lines = [f"Folder contents for {path}:"]
            for item in items:
                item_type = item.get("type", "")
                item_path = item.get("path", "")
                prefix = "[DIR]" if item_type == "dir" else "[FILE]"
                lines.append(f"{prefix} {item_path}")
            return "\n".join(lines)

        if tool_name == "read_file":
            path = data.get("path", "")
            content = data.get("content", "")
            return f"File read: {path}\nContent:\n{content}"

        if tool_name == "write_file":
            return str(data.get("message", "File written."))

        if tool_name == "run_python":
            path = data.get("path", "")
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            returncode = data.get("returncode", None)

            lines = [f"Python execution result: {path}", f"returncode: {returncode}"]

            if stdout:
                lines.append("stdout:")
                lines.append(stdout.rstrip())

            if stderr:
                lines.append("stderr:")
                lines.append(stderr.rstrip())

            return "\n".join(lines)

        if tool_name == "generate_python":
            filename = data.get("filename", "")
            return f"Python code generated for: {filename}"

        if tool_name == "shell":
            cmd = data.get("cmd", "")
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            returncode = data.get("returncode", None)

            lines = [f"Shell command: {cmd}", f"returncode: {returncode}"]

            if stdout:
                lines.append("stdout:")
                lines.append(stdout.rstrip())

            if stderr:
                lines.append("stderr:")
                lines.append(stderr.rstrip())

            return "\n".join(lines)

        if tool_name == "pip_install":
            package = data.get("package", "")
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")

            lines = [f"pip install: {package}"]

            if stdout:
                lines.append("stdout:")
                lines.append(stdout.rstrip())

            if stderr:
                lines.append("stderr:")
                lines.append(stderr.rstrip())

            return "\n".join(lines)

        if tool_name == "list_routes":
            return f"Routes: {data}"

        if tool_name == "restart_flask":
            return f"Restart result: {data}"

        return f"Tool finished: {data}"

    def build_fix_prompt(self, file_path: str, file_content: str, stderr: str) -> str:
        return f"""
You are a Python repair agent.

Your task:
Fix the Python file so it runs successfully.

Rules:
1. Return ONLY full corrected Python code.
2. Do not explain.
3. Do not use markdown.
4. Do not use code fences.
5. Keep it minimal and runnable.
6. Preserve the original intent if possible.

File path:
{file_path}

Current code:
{file_content}

Python error:
{stderr}

Return corrected full Python code only.
""".strip()

    def try_auto_fix(self, file_path: str, stderr: str) -> str | None:
        read_result = run_tool("read_file", {"path": file_path})

        if not read_result.get("success", False):
            return None

        data = read_result.get("data", {}) or {}
        old_code = str(data.get("content", "")).strip()

        if not old_code:
            return None

        prompt = self.build_fix_prompt(
            file_path=file_path,
            file_content=old_code,
            stderr=stderr
        )

        raw = self.llm.generate(prompt).strip()

        if not raw:
            return None

        if raw.startswith("LLM_ERROR:"):
            return None

        fixed_code = self.cleanup_code_block(raw)

        if not fixed_code:
            return None

        return fixed_code

    def resolve_dynamic_args(self, args: dict, results: list) -> dict:
        resolved = dict(args or {})

        marker = resolved.get("__from_previous__")
        if not marker:
            return resolved

        if not results:
            resolved.pop("__from_previous__", None)
            return resolved

        parts = str(marker).split(".")
        if len(parts) != 2:
            resolved.pop("__from_previous__", None)
            return resolved

        target_tool, target_field = parts
        value = None

        for step in reversed(results):
            result = step.get("result", {}) or {}
            tool_name = str(result.get("tool", "")).strip()

            if tool_name == target_tool:
                data = result.get("data", {}) or {}
                value = data.get(target_field)
                break

        resolved.pop("__from_previous__", None)

        if value is not None:
            if target_field == "code":
                value = self.cleanup_code_block(str(value))
                resolved["content"] = value
            else:
                resolved[target_field] = value

        return resolved

    def should_auto_run_after_write(self, user_input: str, step: dict) -> bool:
        tool_name = str(step.get("tool", "")).strip()
        args = step.get("args", {}) or {}
        path = str(args.get("path", "")).strip()

        if tool_name != "write_file":
            return False

        if not path.endswith(".py"):
            return False

        text = str(user_input or "").lower()

        run_signals = [
            "run",
            "execute",
            "create and run",
            "write and run",
            "執行",
            "建立並執行",
        ]

        return any(signal in text for signal in run_signals)

    def build_followup_steps(
        self,
        user_input: str,
        step: dict,
        result: dict,
        fix_attempts: dict
    ) -> list[dict]:
        tool_name = str(step.get("tool", "")).strip()
        args = step.get("args", {}) or {}
        data = result.get("data", {}) or {}

        followups = []

        if tool_name == "generate_python":
            return followups

        if tool_name == "write_file":
            if result.get("success", False) and self.should_auto_run_after_write(user_input, step):
                path = str(args.get("path", "")).strip()
                if path.endswith(".py"):
                    return [{
                        "action": "tool",
                        "tool": "run_python",
                        "args": {
                            "path": path
                        }
                    }]
            return followups

        if tool_name == "run_python":
            path = str(data.get("path", args.get("path", ""))).strip()

            if result.get("success", False):
                return followups

            if not path.endswith(".py"):
                return followups

            current_attempts = int(fix_attempts.get(path, 0))
            if current_attempts >= self.max_fix_attempts:
                return followups

            stderr = str(data.get("stderr", "")).strip()
            if not stderr:
                stderr = str(data.get("message", "")).strip()

            fixed_code = self.try_auto_fix(file_path=path, stderr=stderr)
            if not fixed_code:
                return followups

            fix_attempts[path] = current_attempts + 1

            return [
                {
                    "action": "tool",
                    "tool": "write_file",
                    "args": {
                        "path": path,
                        "content": fixed_code
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

        return followups

    def normalize_plan(self, raw_plan):
        if isinstance(raw_plan, list):
            return raw_plan

        if isinstance(raw_plan, dict):
            action = raw_plan.get("action")

            if action in ["multi_step", "multi_step_execution"]:
                steps = raw_plan.get("steps", [])
                if isinstance(steps, list):
                    return steps
                return [{
                    "action": "reply",
                    "message": f"{action} plan has invalid steps"
                }]

            return [raw_plan]

        return [{
            "action": "reply",
            "message": "plan format is invalid"
        }]

    def run(self, user_input: str) -> dict:
        user_input = str(user_input or "").strip()

        if not user_input:
            return {
                "success": False,
                "mode": "agent_loop",
                "input": "",
                "plan": [],
                "results": [],
                "observations": [],
                "final_answer": "input is required"
            }

        planner_output = self.planner.build_plan(user_input)
        initial_plan = self.normalize_plan(planner_output)

        queue = list(initial_plan)
        executed_plan = []
        results = []
        observations = []
        fix_attempts = {}
        step_index = 0

        while queue and step_index < self.max_steps:
            item = queue.pop(0)
            step_index += 1

            action = item.get("action")

            if action == "reply":
                executed_plan.append(item)
                return {
                    "success": True,
                    "mode": "reply",
                    "input": user_input,
                    "plan": executed_plan,
                    "results": results,
                    "observations": observations,
                    "final_answer": item.get("message", "")
                }

            if action != "tool":
                executed_plan.append(item)
                return {
                    "success": False,
                    "mode": "agent_loop",
                    "input": user_input,
                    "plan": executed_plan,
                    "results": results,
                    "observations": observations,
                    "final_answer": f"Unknown action: {action}"
                }

            tool_name = str(item.get("tool", "")).strip()
            raw_args = item.get("args", {}) or {}
            args = self.resolve_dynamic_args(raw_args, results)

            executed_step = {
                "action": "tool",
                "tool": tool_name,
                "args": args
            }
            executed_plan.append(executed_step)

            result = run_tool(tool_name, args)

            results.append({
                "step": step_index,
                "tool": tool_name,
                "args": args,
                "result": result
            })

            observations.append({
                "step": step_index,
                "observation": result
            })

            followups = self.build_followup_steps(
                user_input=user_input,
                step=executed_step,
                result=result,
                fix_attempts=fix_attempts
            )

            if followups:
                queue = followups + queue
                continue

            if not result.get("success", False):
                return {
                    "success": False,
                    "mode": "agent_loop",
                    "input": user_input,
                    "plan": executed_plan,
                    "results": results,
                    "observations": observations,
                    "final_answer": f"Step {step_index} failed: {tool_name}"
                }

        if queue:
            return {
                "success": False,
                "mode": "agent_loop",
                "input": user_input,
                "plan": executed_plan,
                "results": results,
                "observations": observations,
                "final_answer": f"Max steps reached ({self.max_steps}) before task completion."
            }

        final_answer = self.build_final_answer(results)

        return {
            "success": True,
            "mode": "agent_loop",
            "input": user_input,
            "plan": executed_plan,
            "results": results,
            "observations": observations,
            "final_answer": final_answer
        }

    def interactive(self):
        print(
            f"ZERO Project Agent started "
            f"(model={self.model}, max_steps={self.max_steps}, max_fix_attempts={self.max_fix_attempts})"
        )
        print("Type exit to quit")
        print("-" * 60)

        while True:
            user_text = input("you> ").strip()

            if user_text.lower() in ["exit", "quit"]:
                print("Agent stopped")
                break

            result = self.run(user_text)

            print("\n[Agent Result]")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print("-" * 60)


if __name__ == "__main__":
    agent = ProjectAgent()
    agent.interactive()