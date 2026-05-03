# core/tools/registry.py

from typing import Dict, Callable

_TOOL_REGISTRY: Dict[str, Callable] = {}


def register_tool(name: str, fn: Callable):
    _TOOL_REGISTRY[name] = fn


def get_tool(name: str) -> Callable:
    if name not in _TOOL_REGISTRY:
        raise ValueError(f"Tool not found: {name}")
    return _TOOL_REGISTRY[name]


def list_tools():
    return list(_TOOL_REGISTRY.keys())