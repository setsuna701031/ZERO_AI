from __future__ import annotations

from typing import Any, Dict


def handle_system_mode(
    user_input: str,
    route_result: Dict[str, Any],
    current_mode: str,
    build_final_response_func: Any,
) -> Dict[str, Any]:
    system_action = str(route_result.get("system_action", "")).strip()

    if system_action == "mode_show":
        return build_final_response_func(
            success=True,
            mode="system",
            summary="Current mode displayed.",
            final_answer=f"目前模式：{current_mode}",
            data={
                "user_input": user_input,
                "route_result": route_result,
                "current_mode": current_mode,
            },
            error=None,
        )

    if system_action == "mode_set":
        target_mode = str(route_result.get("target_mode", "")).strip().lower()
        new_mode = target_mode or current_mode

        return build_final_response_func(
            success=True,
            mode="system",
            summary="Mode updated.",
            final_answer=f"模式已切換為：{new_mode}",
            data={
                "user_input": user_input,
                "route_result": route_result,
                "current_mode": new_mode,
            },
            error=None,
        )

    if system_action == "error":
        error_message = str(route_result.get("error", "unknown router error")).strip()

        return build_final_response_func(
            success=False,
            mode="system",
            summary="Router error.",
            final_answer=f"路由器錯誤：{error_message}",
            data={
                "user_input": user_input,
                "route_result": route_result,
            },
            error=error_message,
        )

    return build_final_response_func(
        success=False,
        mode="system",
        summary="Unsupported system route.",
        final_answer="目前不支援這個系統操作。",
        data={
            "user_input": user_input,
            "route_result": route_result,
        },
        error="unsupported system action",
    )