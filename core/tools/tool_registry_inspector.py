from __future__ import annotations

from typing import Any, Dict, List

from core.tool_registry import ToolRegistry


def build_tools_payload(tool_registry: ToolRegistry) -> Dict[str, Any]:
    """
    給 /api/tools 使用的統一輸出

    職責：
    1. 從 ToolRegistry 讀取工具名稱
    2. 從 ToolRegistry 讀取工具定義
    3. 組成 API 可直接使用的 payload
    """
    tool_names: List[str] = tool_registry.list_tool_names()
    tool_definitions: List[Dict[str, Any]] = tool_registry.list_tool_definitions()

    tools_info: List[Dict[str, Any]] = []
    for tool_def in tool_definitions:
        if not isinstance(tool_def, dict):
            continue

        tools_info.append({
            "name": tool_def.get("name", ""),
            "description": tool_def.get("description", ""),
            "parameters": tool_def.get("parameters", {}),
        })

    return {
        "success": True,
        "count": len(tool_names),
        "tool_names": tool_names,
        "tools": tools_info,
    }


def build_tools_debug_payload(tool_registry: ToolRegistry) -> Dict[str, Any]:
    """
    給除錯使用的 registry 狀態輸出
    """
    dump = tool_registry.debug_dump()
    return {
        "success": True,
        "debug": dump,
    }