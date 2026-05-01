from __future__ import annotations

import re
from typing import Any

from core.tools.tool_schema import ToolRequest, ToolResult

class ToolRouter:
    def __init__(self, tool_registry: Any) -> None:
        self.tool_registry = tool_registry

    def route(self, task: dict) -> ToolRequest | None:
        """
        Return:
        {
          "tool": "github_inbox" | "github_outbox" | None,
          "input": {...}
        }
        """
        content = str(task).lower()

        if "github_inbox" in content:
            return ToolRequest(tool="github_inbox", input={"task": task}, source="tool_router", risk_level="low")

        if "github_outbox" in content:
            return ToolRequest(tool="github_outbox", input={"task": task}, source="tool_router", risk_level="low")

        if any(k in content for k in ["review", "analyze", "check pr", "read issue"]):
            return ToolRequest(tool="github_inbox", input={"task": task}, source="tool_router", risk_level="low")

        if (
            any(k in content for k in ["commit", "pull request", "github", "publish"])
            or re.search(r"\bpr\b", content) is not None
        ):
            return ToolRequest(tool="github_outbox", input={"task": task}, source="tool_router", risk_level="low")

        return None

    def dispatch(self, task: dict) -> ToolResult | None:
        route = self.route(task)
        if not route:
            return None
        return self.tool_registry.execute_tool_request(route)
