from __future__ import annotations

import re
from typing import Any, Dict


class ToolRouter:
    def __init__(self, tool_registry: Any) -> None:
        self.tool_registry = tool_registry

    def route(self, task: dict) -> Dict[str, Any] | None:
        """
        Return:
        {
          "tool": "github_inbox" | "github_outbox" | None,
          "input": {...}
        }
        """
        content = str(task).lower()

        if "github_inbox" in content:
            return {
                "tool": "github_inbox",
                "input": {"task": task},
            }

        if "github_outbox" in content:
            return {
                "tool": "github_outbox",
                "input": {"task": task},
            }

        if any(k in content for k in ["review", "analyze", "check pr", "read issue"]):
            return {
                "tool": "github_inbox",
                "input": {"task": task},
            }

        if (
            any(k in content for k in ["commit", "pull request", "github", "publish"])
            or re.search(r"\bpr\b", content) is not None
        ):
            return {
                "tool": "github_outbox",
                "input": {"task": task},
            }

        return None

    def dispatch(self, task: dict) -> Dict[str, Any] | None:
        route = self.route(task)
        if not route:
            return None
        return self.tool_registry.execute_tool(route["tool"], route["input"])
