from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.tools.tool_registry import ToolRegistry
from core.tools.tool_router import ToolRouter
from core.tools.tool_schema import ToolRequest, ToolResult


PREFIX = "[tool-schema-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def main() -> int:
    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    request = ToolRequest(tool="github_outbox", input={"task": "schema test"})
    result = registry.execute_tool_request(request)

    if not isinstance(result, ToolResult):
        return fail(f"execute_tool_request did not return ToolResult: {type(result)}")
    if result.ok is not True:
        return fail(f"ToolResult not ok: {result}")
    if result.tool != "github_outbox":
        return fail(f"unexpected tool: {result.tool}")
    if not (result.output.get("artifacts") or result.output.get("changed_files")):
        return fail(f"missing artifacts/changed_files: {result.output}")
    if "commit" in result.side_effect_level.lower() or "push" in result.side_effect_level.lower():
        return fail(f"side_effect_level implies forbidden mutation: {result.side_effect_level}")
    print(f"{PREFIX} PASS: execute_tool_request returns ToolResult")

    route = ToolRouter(registry).route({"title": "generate commit message"})
    if not isinstance(route, ToolRequest):
        return fail(f"router did not return ToolRequest: {route}")
    if route.tool != "github_outbox":
        return fail(f"router selected wrong tool: {route}")
    print(f"{PREFIX} PASS: router returns ToolRequest")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
