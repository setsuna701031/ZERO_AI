from __future__ import annotations

from typing import Any, Dict


def _extract_text_deep(payload: Any, depth: int = 0) -> str:
    if depth > 12 or payload is None:
        return ""

    if isinstance(payload, str):
        return payload

    if isinstance(payload, dict):
        for key in (
            "text",
            "content",
            "message",
            "final_answer",
            "response",
            "answer",
            "summary",
            "summary_text",
            "stdout",
            "output_text",
        ):
            value = payload.get(key)
            if isinstance(value, str):
                return value

        for nested_key in (
            "result",
            "raw",
            "data",
            "payload",
            "output",
            "previous_result",
            "last_step_result",
            "runtime_execution_result",
            "adapter_payload",
        ):
            nested = payload.get(nested_key)
            text = _extract_text_deep(nested, depth + 1)
            if isinstance(text, str) and text:
                return text

    if isinstance(payload, list):
        for item in reversed(payload):
            text = _extract_text_deep(item, depth + 1)
            if isinstance(text, str) and text:
                return text

    return ""

def _legacy_template_detected(step: Dict[str, Any]) -> bool:
    for key in ("content", "text", "body"):
        value = step.get(key)
        if isinstance(value, str) and "{{previous_result" in value:
            return True
    return False
