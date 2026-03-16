from core.tool_registry import TOOL_REGISTRY


def get_available_tools() -> list[str]:
    return sorted(TOOL_REGISTRY.keys())


def run_tool(tool_name: str, args: dict | None = None) -> dict:
    args = args or {}

    handler = TOOL_REGISTRY.get(tool_name)
    if handler is None:
        return {
            "tool": tool_name,
            "success": False,
            "data": {
                "message": f"unknown tool: {tool_name}",
                "available_tools": get_available_tools()
            }
        }

    try:
        return handler(args)
    except Exception as exc:
        return {
            "tool": tool_name,
            "success": False,
            "data": {
                "message": f"tool execution failed: {exc}"
            }
        }