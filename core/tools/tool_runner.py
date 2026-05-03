# core/tools/tool_runner.py

from core.tools.registry import get_tool


def run_tool(name: str, payload: dict):
    tool = get_tool(name)
    return tool(payload)