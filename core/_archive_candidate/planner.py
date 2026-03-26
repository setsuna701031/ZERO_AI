import json
import re
from core.llm_client import ask_local_llm


SYSTEM_PROMPT = """
You are an AI planner.

Your task is to break the user's request into a short step-by-step plan.

You must reply with JSON only.
Do not add explanation.
Do not add markdown.
Do not use code fences.

The JSON format must be exactly:

{
  "steps": [
    {"step": 1, "task": "first task"},
    {"step": 2, "task": "second task"}
  ]
}
"""


def _extract_json_block(text: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None

    # 先直接假設整段就是 JSON
    if text.startswith("{") and text.endswith("}"):
        return text

    # 嘗試抓第一個 {...} 區塊
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        return match.group(0).strip()

    return None


def _validate_plan(plan: dict) -> bool:
    if not isinstance(plan, dict):
        return False

    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        return False

    for item in steps:
        if not isinstance(item, dict):
            return False
        if "step" not in item or "task" not in item:
            return False

    return True


def create_plan(question: str, model_name: str = "zero_general:latest") -> dict:
    question = (question or "").strip()

    if not question:
        return {
            "success": False,
            "error": "question is empty"
        }

    prompt = f"""{SYSTEM_PROMPT}

User request:
{question}
"""

    result = ask_local_llm(prompt, model_name=model_name)

    if not result.get("success"):
        return {
            "success": False,
            "error": result.get("message", "llm failed"),
            "details": result.get("details", "")
        }

    raw_text = result.get("answer", "").strip()
    json_text = _extract_json_block(raw_text)

    if not json_text:
        return {
            "success": False,
            "error": "planner returned invalid JSON",
            "raw": raw_text
        }

    try:
        plan = json.loads(json_text)
    except Exception:
        return {
            "success": False,
            "error": "planner returned invalid JSON",
            "raw": raw_text
        }

    if not _validate_plan(plan):
        return {
            "success": False,
            "error": "planner returned invalid plan structure",
            "raw": raw_text,
            "parsed": plan
        }

    return {
        "success": True,
        "plan": plan,
        "model": model_name
    }