from __future__ import annotations

import copy
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Dict

from core.tools.tool_controller import (
    ALLOW_TOOL,
    ToolController,
    annotate_tool_result,
    controller_observation,
)
from core.tools.tool_decision import tool_decision_to_tool_call
from core.tools.tool_decision_policy import ToolDecisionPolicy
from core.tools.tool_executor import ToolExecutor
from core.tools.tool_schema import ToolRequest, ToolResult


TERMINAL_STATUSES = {"success", "failed", "blocked", "invalid_tool"}


class ToolCallExecutor:
    def __init__(
        self,
        tool_registry: Any,
        decision_policy: ToolDecisionPolicy | None = None,
        tool_controller: ToolController | None = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.decision_policy = decision_policy or ToolDecisionPolicy()
        self.tool_controller = tool_controller or ToolController()

    def execute_decision(
        self,
        decision: Any,
        *,
        source: str = "agent_loop",
        decision_input: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        policy = self.decision_policy.evaluate(decision, tool_registry=self.tool_registry)
        controller_decision = self.tool_controller.decide(
            proposal=decision,
            policy_recommendation=policy,
            decision_input=decision_input,
        )
        if controller_decision.get("final_decision") != ALLOW_TOOL:
            return controller_observation(controller_decision)
        tool_result = self.execute(
            {
                "tool": policy.get("tool"),
                "args": copy.deepcopy(policy.get("args", {})),
            },
            source=source,
        )
        return annotate_tool_result(tool_result, controller_decision)

    def execute(self, tool_call: Any, *, source: str = "agent_loop") -> Dict[str, Any]:
        normalized = normalize_tool_call(tool_call)
        if not normalized.get("ok"):
            return _standard_result(
                tool=str(normalized.get("tool") or ""),
                args=normalized.get("args") if isinstance(normalized.get("args"), dict) else {},
                status="blocked",
                ok=False,
                error=str(normalized.get("error") or "invalid tool_call"),
            )

        tool_name = str(normalized["tool"])
        args = normalized["args"]
        if self.tool_registry is None:
            return _standard_result(
                tool=tool_name,
                args=args,
                status="blocked",
                ok=False,
                error="tool_registry missing",
            )

        has_tool = getattr(self.tool_registry, "has_tool", None)
        if callable(has_tool) and not has_tool(tool_name):
            return _standard_result(
                tool=tool_name,
                args=args,
                status="invalid_tool",
                ok=False,
                error=f"tool not found: {tool_name}",
            )

        try:
            request = ToolRequest(tool=tool_name, input=args, source=source, risk_level="low")
            get_tool_schema = getattr(self.tool_registry, "get_tool_schema", None)
            if callable(get_tool_schema) and get_tool_schema(tool_name) is not None:
                result = ToolExecutor(self.tool_registry).execute(request)
            else:
                result = self.tool_registry.execute_tool_request(request)
        except Exception as exc:
            return _standard_result(
                tool=tool_name,
                args=args,
                status="failed",
                ok=False,
                error=str(exc),
            )

        result_payload = asdict(result) if is_dataclass(result) else copy.deepcopy(result)
        if isinstance(result, ToolResult):
            output = result.output if isinstance(result.output, dict) else {}
            status = str(output.get("status") or ("success" if result.ok else "failed"))
            if status not in TERMINAL_STATUSES:
                status = "success" if result.ok else "failed"
            return _standard_result(
                tool=result.tool,
                args=args,
                status=status,
                ok=bool(result.ok and status == "success"),
                output=output,
                error=result.error or output.get("error"),
                request_id=result.request_id,
                side_effect_level=result.side_effect_level,
            )

        if isinstance(result_payload, dict):
            output = result_payload.get("output") if isinstance(result_payload.get("output"), dict) else result_payload
            status = str(output.get("status") or ("success" if result_payload.get("ok") else "failed"))
            return _standard_result(
                tool=str(result_payload.get("tool") or tool_name),
                args=args,
                status=status if status in TERMINAL_STATUSES else "failed",
                ok=bool(result_payload.get("ok") and status != "blocked"),
                output=output,
                error=result_payload.get("error") or output.get("error"),
                request_id=result_payload.get("request_id"),
                side_effect_level=str(output.get("side_effect_level") or "none"),
            )

        return _standard_result(tool=tool_name, args=args, status="failed", ok=False, error="invalid tool result")


def normalize_tool_call(tool_call: Any) -> Dict[str, Any]:
    is_explicit_decision = isinstance(tool_call, str) or (
        isinstance(tool_call, dict)
        and ("type" in tool_call or "action" in tool_call)
    )
    if is_explicit_decision:
        parsed = tool_decision_to_tool_call(tool_call)
        if parsed.get("ok") or parsed.get("error"):
            return parsed

    payload = copy.deepcopy(tool_call) if isinstance(tool_call, dict) else {}
    if "tool_call" in payload and isinstance(payload.get("tool_call"), dict):
        payload = copy.deepcopy(payload["tool_call"])
    tool = str(payload.get("tool") or "").strip()
    args = payload.get("args")
    if args is None and isinstance(payload.get("input"), dict):
        args = payload.get("input")
    if args is None:
        args = {}
    if not tool:
        return {"ok": False, "tool": tool, "args": args if isinstance(args, dict) else {}, "error": "tool is required"}
    if not isinstance(args, dict):
        return {"ok": False, "tool": tool, "args": {}, "error": "args must be a dict"}
    return {"ok": True, "tool": tool, "args": args}


def tool_call_trace_event(tool_result: Dict[str, Any]) -> Dict[str, Any]:
    output = tool_result.get("output") if isinstance(tool_result.get("output"), dict) else {}
    trace = output.get("trace") if isinstance(output.get("trace"), dict) else {}
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "tool_call",
        "tool": tool_result.get("tool"),
        "status": tool_result.get("status"),
        "ok": bool(tool_result.get("ok")),
        "args_summary": summarize_payload(tool_result.get("args", {})),
        "result_summary": summarize_payload(tool_result.get("output", {})),
        "duration_ms": trace.get("duration_ms"),
        "error": tool_result.get("error"),
        "request_id": tool_result.get("request_id"),
        "final_decision": tool_result.get("final_decision"),
    }


def summarize_payload(payload: Any) -> Any:
    if payload is None or isinstance(payload, (bool, int, float)):
        return payload
    if isinstance(payload, str):
        return payload if len(payload) <= 160 else f"{payload[:160]}... <truncated len={len(payload)}>"
    if isinstance(payload, dict):
        summary: Dict[str, Any] = {}
        for key, value in list(payload.items())[:10]:
            key_text = str(key)
            if key_text.lower() in {"content", "file_content", "stdout", "stderr"}:
                summary[key_text] = {"type": type(value).__name__, "length": len(str(value))}
            else:
                summary[key_text] = summarize_payload(value)
        if len(payload) > 10:
            summary["truncated_keys"] = len(payload) - 10
        return summary
    if isinstance(payload, list):
        return [summarize_payload(item) for item in payload[:8]]
    return str(payload)


def _standard_result(
    *,
    tool: str,
    args: Dict[str, Any],
    status: str,
    ok: bool,
    output: Dict[str, Any] | None = None,
    error: Any = None,
    request_id: str | None = None,
    side_effect_level: str = "none",
) -> Dict[str, Any]:
    normalized_output = copy.deepcopy(output or {})
    if "observation" not in normalized_output:
        normalized_output["observation"] = {
            "type": "tool_error" if not ok else "tool_result",
            "summary": str(error or status or ""),
            "data": {},
        }
    return {
        "ok": bool(ok),
        "tool": tool,
        "args": copy.deepcopy(args),
        "status": status,
        "output": normalized_output,
        "error": None if not error else str(error),
        "request_id": request_id,
        "side_effect_level": side_effect_level,
    }
