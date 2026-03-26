import json
from core.llm_client import ask_local_llm
from core.tool_router import get_available_tools


SYSTEM_PROMPT = """
You are an AI tool selector.

If the user's request requires a tool, respond in JSON:

{
 "tool": "tool_name",
 "args": {}
}

If no tool is required, respond:

{
 "tool": null
}

Available tools:
"""


def select_tool(question: str):

    tools = get_available_tools()

    prompt = (
        SYSTEM_PROMPT
        + json.dumps(tools)
        + "\n\nUser question:\n"
        + question
    )

    result = ask_local_llm(prompt)

    if not result.get("success"):
        return None

    text = result.get("answer", "").strip()

    try:
        data = json.loads(text)
        return data.get("tool"), data.get("args", {})
    except Exception:
        return None