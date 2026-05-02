from __future__ import annotations

import copy
import time
from dataclasses import asdict
from typing import Any, Dict
from uuid import uuid4

from core.tools.tool_policy import evaluate_l4_tool_request
from core.tools.tool_schema import ToolRequest, ToolResult, ToolSpec


class ToolExecutor:
    """
    L4 tool executor.

    The scheduler should not know tool names, schemas, or policy details. This
    object owns the contract between an agent loop and concrete tools.
    """

    def __init__(self, registry: Any) -> None:
        self.registry = registry

    def execute(self, request: ToolRequest) -> ToolResult:
        started = time.time()
        if not request.request_id:
            request.request_id = str(uuid4())

        spec = self._get_spec(request.tool)
        if spec is None:
            return self._blocked(
                request=request,
                reason="tool_schema_not_found",
                started=started,
            )

        validation_error = self._validate_args(spec, request.input)
        if validation_error:
            return self._blocked(
                request=request,
                reason=validation_error,
                spec=spec,
                started=started,
            )

        policy = evaluate_l4_tool_request(
            tool_name=spec.name,
            args=request.input,
            tool_class=spec.tool_class,
            side_effect_level=spec.side_effect_level,
            scope=spec.scope,
        )
        if policy.get("ok") is not True:
            return self._blocked(
                request=request,
                reason=str(policy.get("reason") or "policy_blocked"),
                spec=spec,
                policy=policy,
                started=started,
            )

        try:
            raw_result = self.registry.execute_tool_request(request)
        except Exception as exc:
            return ToolResult(
                ok=False,
                tool=request.tool,
                output=self._envelope(
                    status="failed",
                    request=request,
                    spec=spec,
                    observation={
                        "type": "tool_error",
                        "summary": str(exc),
                        "data": {},
                    },
                    policy=policy,
                    started=started,
                ),
                error=str(exc),
                side_effect_level=spec.side_effect_level,
                request_id=request.request_id,
            )

        output = raw_result.output if isinstance(raw_result.output, dict) else {}
        status = str(output.get("status") or ("success" if raw_result.ok else "failed"))
        observation = output.get("observation")
        if not isinstance(observation, dict):
            observation = {
                "type": "tool_result" if raw_result.ok else "tool_error",
                "summary": str(output.get("summary") or raw_result.error or status),
                "data": copy.deepcopy(output),
            }
        output = copy.deepcopy(output)
        output.update(
            self._envelope(
                status=status,
                request=request,
                spec=spec,
                observation=observation,
                policy=policy,
                started=started,
            )
        )
        return ToolResult(
            ok=bool(raw_result.ok and status == "success"),
            tool=str(raw_result.tool or request.tool),
            output=output,
            error=raw_result.error or output.get("error"),
            side_effect_level=spec.side_effect_level,
            request_id=request.request_id,
        )

    def _get_spec(self, tool_name: str) -> ToolSpec | None:
        get_tool_schema = getattr(self.registry, "get_tool_schema", None)
        if not callable(get_tool_schema):
            return None
        spec = get_tool_schema(tool_name)
        return spec if isinstance(spec, ToolSpec) else None

    def _validate_args(self, spec: ToolSpec, args: Dict[str, Any]) -> str:
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

    def _blocked(
        self,
        *,
        request: ToolRequest,
        reason: str,
        started: float,
        spec: ToolSpec | None = None,
        policy: Dict[str, Any] | None = None,
    ) -> ToolResult:
        return ToolResult(
            ok=False,
            tool=str(request.tool or ""),
            output=self._envelope(
                status="blocked",
                request=request,
                spec=spec,
                observation={
                    "type": "tool_error",
                    "summary": reason,
                    "data": {},
                },
                policy=policy or {},
                started=started,
            ),
            error=reason,
            side_effect_level="" if spec is None else spec.side_effect_level,
            request_id=request.request_id,
        )

    def _envelope(
        self,
        *,
        status: str,
        request: ToolRequest,
        spec: ToolSpec | None,
        observation: Dict[str, Any],
        policy: Dict[str, Any] | None = None,
        started: float,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "tool": request.tool,
            "request_id": request.request_id,
            "schema": {} if spec is None else spec.to_dict(),
            "policy": dict(policy or {}),
            "observation": copy.deepcopy(observation),
            "trace": {
                "tool_call_id": request.request_id,
                "tool": request.tool,
                "args": _summarize_args(request.input),
                "duration_ms": int((time.time() - started) * 1000),
                "source": request.source,
            },
        }


def _summarize_args(args: Any) -> Dict[str, Any]:
    payload = args if isinstance(args, dict) else {}
    summary: Dict[str, Any] = {}
    for key, value in payload.items():
        if str(key).lower() == "content":
            summary[str(key)] = {"type": type(value).__name__, "length": len(str(value))}
        else:
            summary[str(key)] = copy.deepcopy(value)
    return summary
