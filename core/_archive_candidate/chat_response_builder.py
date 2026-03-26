from __future__ import annotations

from typing import Any, Dict


def build_chat_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    將 Agent 回傳結果整理成 /api/chat 可直接回傳的格式
    """
    if not isinstance(result, dict):
        return {
            "success": False,
            "error": "agent returned invalid result",
            "response": "",
            "result": result,
        }

    response_text = (
        result.get("final_answer")
        or result.get("summary")
        or result.get("response")
        or ""
    )

    return {
        "success": bool(result.get("success", True)),
        "response": response_text,
        "result": result,
    }


def build_chat_error_payload(error_message: str) -> Dict[str, Any]:
    """
    將例外錯誤整理成 /api/chat 錯誤輸出格式
    """
    return {
        "success": False,
        "error": error_message,
        "response": f"Server error: {error_message}",
    }