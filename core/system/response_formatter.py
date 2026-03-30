from typing import Any, Dict, Optional


class ResponseFormatter:
    """
    專門負責 ZERO AgentLoop 的統一回傳格式。

    目標：
    1. 統一 success / mode / summary / data / error
    2. 提供 chat / tool / command / confirm / system 專用建構方法
    3. 讓 AgentLoop 專注在流程控制，而不是輸出格式細節
    """

    @staticmethod
    def build(
        success: bool,
        mode: str,
        summary: str,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        if data is None:
            data = {}

        if not isinstance(data, dict):
            data = {"value": data}

        return {
            "success": bool(success),
            "mode": str(mode),
            "summary": str(summary),
            "data": data,
            "error": error,
        }

    @staticmethod
    def build_system(
        success: bool,
        summary: str,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        return ResponseFormatter.build(
            success=success,
            mode="system",
            summary=summary,
            data=data,
            error=error,
        )

    @staticmethod
    def build_confirm(
        summary: str,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        return ResponseFormatter.build(
            success=True,
            mode="confirm",
            summary=summary,
            data=data,
            error=error,
        )

    @staticmethod
    def build_chat(
        summary: str,
        reply: str,
        llm_used: bool,
        used_fallback: bool,
        llm_error: Optional[str],
        details: Optional[list] = None,
        model: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        if details is None:
            details = []

        return ResponseFormatter.build(
            success=success,
            mode="chat",
            summary=summary,
            data={
                "reply": reply,
                "llm_used": bool(llm_used),
                "used_fallback": bool(used_fallback),
                "llm_error": llm_error,
                "details": details,
                "model": model,
            },
            error=error,
        )

    @staticmethod
    def build_tool_success(
        summary: str,
        tool_name: str,
        tool_input: Any,
        tool_result: Any,
    ) -> Dict[str, Any]:
        return ResponseFormatter.build(
            success=True,
            mode="tool",
            summary=summary,
            data={
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_result": tool_result,
            },
            error=None,
        )

    @staticmethod
    def build_tool_failure(
        summary: str,
        tool_name: Optional[str],
        tool_input: Any,
        error: str,
    ) -> Dict[str, Any]:
        return ResponseFormatter.build(
            success=False,
            mode="tool",
            summary=summary,
            data={
                "tool_name": tool_name,
                "tool_input": tool_input,
            },
            error=error,
        )

    @staticmethod
    def build_command_success(
        summary: str,
        command_name: str,
        command_args: Any,
        command_result: Any,
    ) -> Dict[str, Any]:
        return ResponseFormatter.build(
            success=True,
            mode="command",
            summary=summary,
            data={
                "command_name": command_name,
                "command_args": command_args,
                "command_result": command_result,
            },
            error=None,
        )

    @staticmethod
    def build_command_failure(
        summary: str,
        command_name: Optional[str],
        command_args: Any,
        error: str,
    ) -> Dict[str, Any]:
        return ResponseFormatter.build(
            success=False,
            mode="command",
            summary=summary,
            data={
                "command_name": command_name,
                "command_args": command_args,
            },
            error=error,
        )