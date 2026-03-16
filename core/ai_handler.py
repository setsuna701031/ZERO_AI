from core.intent_parser import parse_intent
from core.tool_router import run_tool, get_available_tools
from core.llm_client import ask_local_llm


def _build_chat_response(question: str, llm_result: dict) -> dict:
    if llm_result.get("success"):
        return {
            "status": "ok",
            "mode": "llm",
            "question": question,
            "answer": llm_result.get("answer", ""),
            "llm_backend": llm_result.get("backend"),
            "llm_model": llm_result.get("model"),
            "available_tools": get_available_tools(),
        }

    return {
        "status": "error",
        "mode": "llm",
        "question": question,
        "answer": "",
        "llm_backend": llm_result.get("backend"),
        "llm_model": llm_result.get("model"),
        "error": llm_result.get("message", "llm failed"),
        "details": llm_result.get("details", ""),
        "available_tools": get_available_tools(),
    }


def _build_tool_response(question: str, intent_result: dict, tool_result: dict) -> dict:
    success = tool_result.get("success", False)
    tool_name = tool_result.get("tool")
    data = tool_result.get("data", {})

    return {
        "status": "ok" if success else "error",
        "mode": "tool",
        "question": question,
        "intent": intent_result,
        "tool_name": tool_name,
        "tool_success": success,
        "tool_result": data,
        "available_tools": get_available_tools(),
    }


def handle_ai_ask(data: dict) -> dict:
    question = str(data.get("question", "")).strip()

    if not question:
        return {
            "status": "error",
            "mode": "validation",
            "error": "question is required",
            "answer": "",
            "question": "",
            "available_tools": get_available_tools(),
        }

    intent_result = parse_intent(question)

    if intent_result["intent"] == "empty":
        return {
            "status": "error",
            "mode": "validation",
            "error": "empty question",
            "question": question,
            "available_tools": get_available_tools(),
        }

    if intent_result["intent"] == "tool_call":
        tool_result = run_tool(
            tool_name=intent_result["tool"],
            args=intent_result.get("args", {})
        )
        return _build_tool_response(question, intent_result, tool_result)

    llm_result = ask_local_llm(question)
    return _build_chat_response(question, llm_result)