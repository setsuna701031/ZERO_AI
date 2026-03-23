from __future__ import annotations

from typing import Any, Dict, Optional

from tool_result_formatter import build_tool_final_answer, extract_tool_error


def handle_tool_mode(
    user_input: str,
    route_result: Dict[str, Any],
    tool_registry: Any,
    build_final_response_func: Any,
) -> Dict[str, Any]:
    tool_name = str(route_result.get("tool_name", "")).strip()
    arguments = route_result.get("arguments", {})

    if not tool_name:
        return build_final_response_func(
            success=False,
            mode="tool",
            summary="Tool mode selected but tool name is missing.",
            final_answer="工具模式已觸發，但缺少工具名稱。",
            data={
                "user_input": user_input,
                "route_result": route_result,
            },
            error="tool_name is missing",
        )

    if not isinstance(arguments, dict):
        arguments = {}

    if tool_registry is None:
        return build_final_response_func(
            success=False,
            mode="tool",
            summary="Tool registry is not initialized.",
            final_answer="工具註冊中心尚未初始化。",
            data={
                "user_input": user_input,
                "tool_name": tool_name,
                "arguments": arguments,
            },
            error="tool_registry is not initialized",
        )

    try:
        tool_result = tool_registry.execute_tool(tool_name, arguments)
    except Exception as exc:
        return build_final_response_func(
            success=False,
            mode="tool",
            summary="Tool execution crashed.",
            final_answer=f"工具執行失敗：{exc}",
            data={
                "user_input": user_input,
                "tool_name": tool_name,
                "arguments": arguments,
            },
            error=str(exc),
        )

    return format_tool_result(
        user_input=user_input,
        tool_name=tool_name,
        arguments=arguments,
        tool_result=tool_result,
        route_result=route_result,
        build_final_response_func=build_final_response_func,
    )


def format_tool_result(
    user_input: str,
    tool_name: str,
    arguments: Dict[str, Any],
    tool_result: Any,
    route_result: Dict[str, Any],
    build_final_response_func: Any,
) -> Dict[str, Any]:
    success = True
    error_message: Optional[str] = None

    if isinstance(tool_result, dict):
        if "ok" in tool_result:
            success = bool(tool_result.get("ok"))
        elif "success" in tool_result:
            success = bool(tool_result.get("success"))

        error_message = extract_tool_error(tool_result)

    final_answer = build_tool_final_answer(
        tool_name=tool_name,
        success=success,
        tool_result=tool_result,
        error_message=error_message,
    )

    summary = f"Tool executed: {tool_name}" if success else f"Tool failed: {tool_name}"

    return build_final_response_func(
        success=success,
        mode="tool",
        summary=summary,
        final_answer=final_answer,
        data={
            "user_input": user_input,
            "tool_name": tool_name,
            "arguments": arguments,
            "tool_result": tool_result,
            "route_result": route_result,
        },
        error=error_message,
    )