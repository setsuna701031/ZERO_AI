from __future__ import annotations
from typing import Any, Dict, List


class Planner:
    """
    Very simple planner (rule-based first version)
    Later can be replaced by LLM planner.
    """

    def make_plan(self, user_input: str, route_result: Dict[str, Any]) -> Dict[str, Any]:
        text = (user_input or "").strip()

        if text == "":
            return {"ok": False, "steps": []}

        steps: List[Dict[str, Any]] = []

        # Workspace commands
        if text.startswith("ws "):
            parts = text.split()

            if len(parts) >= 2:
                cmd = parts[1]

                if cmd == "ls":
                    path = parts[2] if len(parts) >= 3 else "."
                    steps.append({
                        "tool": "workspace_tool",
                        "args": {
                            "action": "list_files",
                            "path": path
                        }
                    })

                elif cmd == "read" and len(parts) >= 3:
                    steps.append({
                        "tool": "workspace_tool",
                        "args": {
                            "action": "read_file",
                            "path": parts[2]
                        }
                    })

                elif cmd == "write" and len(parts) >= 4:
                    steps.append({
                        "tool": "workspace_tool",
                        "args": {
                            "action": "write_file",
                            "path": parts[2],
                            "content": " ".join(parts[3:])
                        }
                    })

                elif cmd == "append" and len(parts) >= 4:
                    steps.append({
                        "tool": "workspace_tool",
                        "args": {
                            "action": "append_file",
                            "path": parts[2],
                            "content": " ".join(parts[3:])
                        }
                    })

                elif cmd == "mkdir" and len(parts) >= 3:
                    steps.append({
                        "tool": "workspace_tool",
                        "args": {
                            "action": "make_dir",
                            "path": parts[2]
                        }
                    })

        # Command tool
        elif text.startswith("cmd:"):
            command = text[4:].strip()
            steps.append({
                "tool": "command_tool",
                "args": {
                    "command": command
                }
            })

        return {
            "ok": True,
            "steps": steps
        }