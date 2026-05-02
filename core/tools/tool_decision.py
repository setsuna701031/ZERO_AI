from __future__ import annotations

import copy
import json
from typing import Any, Dict


def parse_tool_decision(value: Any) -> Dict[str, Any]:
    payload = _load_payload(value)
    if not isinstance(payload, dict):
        return _parsed(False, error="tool decision must be a JSON object")

    if isinstance(payload.get("action"), dict):
        payload = copy.deepcopy(payload["action"])

    decision_type = str(payload.get("type") or "").strip()
    if decision_type != "tool_call":
        return _parsed(
            False,
            error="decision is not a tool_call",
            decision_type=decision_type,
            is_tool_call=False,
        )

    tool = str(payload.get("tool") or "").strip()
    args = payload.get("args")
    if args is None and isinstance(payload.get("input"), dict):
        args = payload.get("input")
    if args is None:
        args = {}

    if not tool:
        return _parsed(False, error="tool is required", decision_type=decision_type)
    if not isinstance(args, dict):
        return _parsed(False, error="args must be an object", decision_type=decision_type, tool=tool)

    return _parsed(
        True,
        decision_type=decision_type,
        is_tool_call=True,
        tool=tool,
        args=args,
    )


def tool_decision_to_tool_call(value: Any) -> Dict[str, Any]:
    parsed = parse_tool_decision(value)
    if not parsed.get("ok"):
        return parsed
    return {
        "ok": True,
        "tool": parsed["tool"],
        "args": copy.deepcopy(parsed["args"]),
    }


def _load_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            return None
    return None


def _parsed(
    ok: bool,
    *,
    error: str = "",
    decision_type: str = "",
    is_tool_call: bool = False,
    tool: str = "",
    args: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "ok": bool(ok),
        "is_tool_call": bool(is_tool_call),
        "type": decision_type,
        "tool": tool,
        "args": copy.deepcopy(args or {}),
        "error": error,
    }
