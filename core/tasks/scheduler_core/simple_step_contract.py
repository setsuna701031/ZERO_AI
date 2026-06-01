from __future__ import annotations

import copy
import json
from typing import Any, Dict, Optional


_TEMPLATE_KEYS = (
    "{{previous_result}}",
    "{{previous_result_text}}",
    "{{last_result}}",
    "{{file_content}}",
)

_TEXT_KEYS = (
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
)

_NESTED_KEYS = (
    "result",
    "raw",
    "data",
    "payload",
    "output",
    "previous_result",
    "last_step_result",
    "adapter_payload",
    "runtime_execution_result",
)


def has_simple_template(value: Any) -> bool:
    """Return True when a simple-runtime text value contains supported placeholders.

    This module is intentionally scoped to the Scheduler simple-runtime path.
    It does not import StepExecutor and it does not try to merge the two runtime
    implementations.  Its job is only to make the simple runtime honor the same
    planner payload contract for previous-result placeholders.
    """
    if not isinstance(value, str):
        return False
    return any(token in value for token in _TEMPLATE_KEYS)


def previous_result_from_task(task: Optional[Dict[str, Any]]) -> Any:
    """Pick the latest completed step result from a simple-runtime task record."""
    if not isinstance(task, dict):
        return None

    last_step_result = task.get("last_step_result")
    if last_step_result not in (None, "", {}, []):
        return copy.deepcopy(last_step_result)

    step_results = task.get("step_results")
    if isinstance(step_results, list):
        for item in reversed(step_results):
            if item not in (None, "", {}, []):
                return copy.deepcopy(item)

    results = task.get("results")
    if isinstance(results, list):
        for item in reversed(results):
            if item not in (None, "", {}, []):
                return copy.deepcopy(item)

    return None


def extract_text_from_result(payload: Any, *, max_depth: int = 12) -> str:
    """Extract human-facing text from nested simple-runtime result payloads."""
    if max_depth <= 0 or payload is None:
        return ""

    if isinstance(payload, str):
        return payload

    if isinstance(payload, (int, float, bool)):
        return str(payload)

    if isinstance(payload, dict):
        for key in _TEXT_KEYS:
            value = payload.get(key)
            if isinstance(value, str):
                return value

        for key in _NESTED_KEYS:
            nested = payload.get(key)
            text = extract_text_from_result(nested, max_depth=max_depth - 1)
            if text:
                return text

        # Last resort: if this is a structured non-empty result, keep a stable
        # JSON representation instead of silently returning an empty string.
        try:
            if payload:
                return json.dumps(payload, ensure_ascii=False, indent=2)
        except Exception:
            return str(payload)

    if isinstance(payload, list):
        for item in reversed(payload):
            text = extract_text_from_result(item, max_depth=max_depth - 1)
            if text:
                return text

    return ""


def previous_text_from_task(task: Optional[Dict[str, Any]]) -> str:
    return extract_text_from_result(previous_result_from_task(task))


def render_simple_step_template(value: Any, *, task: Optional[Dict[str, Any]], step: Optional[Dict[str, Any]] = None) -> str:
    """Render simple-runtime planner placeholders using the task's last result.

    Supported placeholders:
    - {{previous_result}}
    - {{previous_result_text}}
    - {{last_result}}
    - {{file_content}}

    This is deliberately a small simple-runtime contract layer, not a copy of
    StepExecutor internals.
    """
    text = "" if value is None else str(value)
    if not has_simple_template(text):
        return text

    previous_text = previous_text_from_task(task)
    replacements = {
        "{{previous_result}}": previous_text,
        "{{previous_result_text}}": previous_text,
        "{{last_result}}": previous_text,
        "{{file_content}}": previous_text,
    }
    for token, replacement in replacements.items():
        text = text.replace(token, replacement)

    return text
