from __future__ import annotations

import copy
from typing import Any, Dict

from core.tools.tool_decision import parse_tool_decision
from core.tools.tool_policy import evaluate_l4_tool_request
from core.tools.tool_schema import ToolSpec


ALLOWED_L5_DECISION_TOOLS = {
    "read_file",
    "write_file",
    "list_dir",
    "web_search_draft",
    "github_draft_bundle",
}


class ToolDecisionPolicy:
    """
    Narrow L5 policy for LLM-originated tool decisions.

    The policy decides whether a parsed decision may reach the executor. It
    does not invoke tools and it does not know concrete tool implementations.
    """

    def __init__(self, allowed_tools: set[str] | None = None) -> None:
        self.allowed_tools = set(allowed_tools or ALLOWED_L5_DECISION_TOOLS)

    def evaluate(self, decision: Any, *, tool_registry: Any) -> Dict[str, Any]:
        parsed = parse_tool_decision(decision)
        if parsed.get("ok") is not True:
            if parsed.get("is_tool_call") is False:
                return _policy_result(
                    ok=True,
                    status="no_tool",
                    reason=str(parsed.get("error") or "no tool_call decision"),
                    parsed=parsed,
                )
            return _policy_result(
                ok=False,
                status="invalid_args",
                reason=str(parsed.get("error") or "invalid tool_call decision"),
                parsed=parsed,
            )

        tool = str(parsed.get("tool") or "").strip()
        args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
        canonical = _canonical_tool_name(tool_registry, tool) or tool

        if canonical not in self.allowed_tools:
            if _registry_has_tool(tool_registry, tool):
                return _policy_result(
                    ok=False,
                    status="denied",
                    reason="l5_tool_not_allowed",
                    parsed=parsed,
                    tool=canonical,
                    args=args,
                )
            return _policy_result(
                ok=False,
                status="invalid_tool",
                reason=f"tool not found: {tool}",
                parsed=parsed,
                tool=tool,
                args=args,
            )

        spec = _tool_schema(tool_registry, canonical)
        if spec is None:
            return _policy_result(
                ok=False,
                status="invalid_tool",
                reason="tool_schema_not_found",
                parsed=parsed,
                tool=canonical,
                args=args,
            )

        validation_error = _validate_args(spec, args)
        if validation_error:
            return _policy_result(
                ok=False,
                status="invalid_args",
                reason=validation_error,
                parsed=parsed,
                tool=canonical,
                args=args,
                schema=spec.to_dict(),
            )

        l4_policy = evaluate_l4_tool_request(
            tool_name=spec.name,
            args=args,
            tool_class=spec.tool_class,
            side_effect_level=spec.side_effect_level,
            scope=spec.scope,
        )
        if l4_policy.get("ok") is not True:
            return _policy_result(
                ok=False,
                status="denied",
                reason=str(l4_policy.get("reason") or "policy_denied"),
                parsed=parsed,
                tool=canonical,
                args=args,
                schema=spec.to_dict(),
                policy=l4_policy,
            )

        return _policy_result(
            ok=True,
            status="allowed",
            reason=str(l4_policy.get("reason") or "allowed"),
            parsed=parsed,
            tool=canonical,
            args=args,
            schema=spec.to_dict(),
            policy=l4_policy,
        )


def policy_observation(decision: Dict[str, Any]) -> Dict[str, Any]:
    status = str(decision.get("status") or "blocked")
    reason = str(decision.get("reason") or status)
    tool = str(decision.get("tool") or "")
    args = decision.get("args") if isinstance(decision.get("args"), dict) else {}
    return {
        "ok": status == "no_tool",
        "tool": tool,
        "args": copy.deepcopy(args),
        "status": status,
        "output": {
            "status": status,
            "tool": tool,
            "policy": copy.deepcopy(decision.get("policy") or {}),
            "observation": {
                "type": "no_tool" if status == "no_tool" else "tool_error",
                "summary": reason,
                "data": {
                    "status": status,
                    "reason": reason,
                },
            },
            "trace": {
                "tool_call_id": None,
                "tool": tool,
                "args": _summarize_args(args),
                "duration_ms": 0,
                "source": "tool_decision_policy",
            },
        },
        "error": None if status == "no_tool" else reason,
        "request_id": None,
        "side_effect_level": "none",
    }


def _policy_result(
    *,
    ok: bool,
    status: str,
    reason: str,
    parsed: Dict[str, Any],
    tool: str = "",
    args: Dict[str, Any] | None = None,
    schema: Dict[str, Any] | None = None,
    policy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "ok": bool(ok),
        "status": status,
        "reason": reason,
        "tool": tool or str(parsed.get("tool") or ""),
        "args": copy.deepcopy(args if isinstance(args, dict) else parsed.get("args", {})),
        "schema": copy.deepcopy(schema or {}),
        "policy": copy.deepcopy(policy or {}),
        "parsed": copy.deepcopy(parsed),
    }


def _canonical_tool_name(tool_registry: Any, tool: str) -> str:
    get_canonical_name = getattr(tool_registry, "get_canonical_name", None)
    if callable(get_canonical_name):
        return str(get_canonical_name(tool) or "")
    return str(tool or "").strip().lower()


def _registry_has_tool(tool_registry: Any, tool: str) -> bool:
    has_tool = getattr(tool_registry, "has_tool", None)
    if callable(has_tool):
        return bool(has_tool(tool))
    return False


def _tool_schema(tool_registry: Any, tool: str) -> ToolSpec | None:
    get_tool_schema = getattr(tool_registry, "get_tool_schema", None)
    if not callable(get_tool_schema):
        return None
    spec = get_tool_schema(tool)
    return spec if isinstance(spec, ToolSpec) else None


def _validate_args(spec: ToolSpec, args: Dict[str, Any]) -> str:
    payload = args if isinstance(args, dict) else {}
    for name in spec.required_parameters:
        if name not in payload or payload.get(name) in (None, ""):
            return f"missing_required_arg:{name}"

    by_name = {item.name: item for item in spec.parameters}
    for name, value in payload.items():
        parameter = by_name.get(name)
        if parameter is None:
            continue
        if parameter.type == "string" and not isinstance(value, str):
            return f"invalid_arg_type:{name}:string"
        if parameter.type == "boolean" and not isinstance(value, bool):
            return f"invalid_arg_type:{name}:boolean"
        if parameter.type == "integer" and not isinstance(value, int):
            return f"invalid_arg_type:{name}:integer"
        if parameter.type == "list" and not isinstance(value, list):
            return f"invalid_arg_type:{name}:list"
    return ""


def _summarize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for key, value in (args or {}).items():
        if str(key).lower() == "content":
            summary[str(key)] = {"type": type(value).__name__, "length": len(str(value))}
        else:
            summary[str(key)] = copy.deepcopy(value)
    return summary
