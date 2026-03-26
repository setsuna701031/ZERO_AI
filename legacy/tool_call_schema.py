import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


ALLOWED_RESPONSE_TYPES = {"final", "tool_call"}


@dataclass
class ToolCallDecision:
    """
    LLM structured response for agent tool calling.
    """

    response_type: str
    message: str = ""
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    parse_error: Optional[str] = None

    @property
    def is_final(self) -> bool:
        return self.response_type == "final"

    @property
    def is_tool_call(self) -> bool:
        return self.response_type == "tool_call"

    @property
    def is_valid(self) -> bool:
        if self.parse_error:
            return False

        if self.response_type not in ALLOWED_RESPONSE_TYPES:
            return False

        if self.is_final:
            return isinstance(self.message, str)

        if self.is_tool_call:
            return (
                isinstance(self.tool_name, str)
                and self.tool_name.strip() != ""
                and isinstance(self.arguments, dict)
            )

        return False


def build_final_decision(message: str, raw_text: str = "") -> ToolCallDecision:
    return ToolCallDecision(
        response_type="final",
        message=message if isinstance(message, str) else str(message),
        raw_text=raw_text
    )


def build_tool_call_decision(
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None,
    raw_text: str = ""
) -> ToolCallDecision:
    return ToolCallDecision(
        response_type="tool_call",
        tool_name=tool_name if isinstance(tool_name, str) else str(tool_name),
        arguments=arguments if isinstance(arguments, dict) else {},
        raw_text=raw_text
    )


def build_error_decision(error_message: str, raw_text: str = "") -> ToolCallDecision:
    return ToolCallDecision(
        response_type="final",
        message="",
        raw_text=raw_text,
        parse_error=error_message
    )


def _extract_json_block(text: str) -> str:
    """
    Try to extract the JSON object from:
    1. pure JSON text
    2. markdown fenced code block
    3. text containing one top-level JSON object
    """
    if not isinstance(text, str):
        return ""

    stripped = text.strip()
    if not stripped:
        return ""

    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    if "```json" in stripped:
        start = stripped.find("```json")
        if start != -1:
            start = stripped.find("\n", start)
            end = stripped.rfind("```")
            if start != -1 and end != -1 and end > start:
                candidate = stripped[start:end].strip()
                if candidate.startswith("{") and candidate.endswith("}"):
                    return candidate

    if "```" in stripped:
        first = stripped.find("```")
        second = stripped.find("\n", first)
        third = stripped.rfind("```")
        if first != -1 and second != -1 and third != -1 and third > second:
            candidate = stripped[second:third].strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return candidate

    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = stripped[first_brace:last_brace + 1].strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            return candidate

    return ""


def parse_tool_call_response(raw_text: str) -> ToolCallDecision:
    """
    Parse LLM text into ToolCallDecision.

    Expected formats:

    final:
    {
      "type": "final",
      "message": "..."
    }

    tool_call:
    {
      "type": "tool_call",
      "tool_name": "file_tool",
      "arguments": {
        "action": "write_file",
        "path": "notes.txt",
        "content": "hello"
      }
    }
    """
    if not isinstance(raw_text, str) or raw_text.strip() == "":
        return build_error_decision("LLM response is empty.", raw_text=str(raw_text))

    json_text = _extract_json_block(raw_text)
    if not json_text:
        return build_error_decision("No valid JSON object found in LLM response.", raw_text=raw_text)

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        return build_error_decision(f"JSON decode error: {exc}", raw_text=raw_text)

    if not isinstance(data, dict):
        return build_error_decision("Parsed JSON is not an object.", raw_text=raw_text)

    response_type = data.get("type")
    if response_type not in ALLOWED_RESPONSE_TYPES:
        return build_error_decision(
            f"Invalid response type: {response_type}",
            raw_text=raw_text
        )

    if response_type == "final":
        message = data.get("message", "")
        if not isinstance(message, str):
            return build_error_decision(
                "Field 'message' must be a string for final response.",
                raw_text=raw_text
            )
        return build_final_decision(message=message, raw_text=raw_text)

    tool_name = data.get("tool_name", "")
    arguments = data.get("arguments", {})

    if not isinstance(tool_name, str) or tool_name.strip() == "":
        return build_error_decision(
            "Field 'tool_name' must be a non-empty string for tool_call.",
            raw_text=raw_text
        )

    if not isinstance(arguments, dict):
        return build_error_decision(
            "Field 'arguments' must be an object/dict for tool_call.",
            raw_text=raw_text
        )

    return build_tool_call_decision(
        tool_name=tool_name.strip(),
        arguments=arguments,
        raw_text=raw_text
    )


def decision_to_dict(decision: ToolCallDecision) -> Dict[str, Any]:
    return {
        "response_type": decision.response_type,
        "message": decision.message,
        "tool_name": decision.tool_name,
        "arguments": decision.arguments,
        "raw_text": decision.raw_text,
        "parse_error": decision.parse_error,
        "is_valid": decision.is_valid,
        "is_final": decision.is_final,
        "is_tool_call": decision.is_tool_call,
    }