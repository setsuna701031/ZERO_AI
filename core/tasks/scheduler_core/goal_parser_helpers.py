from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from core.tasks.scheduler_core.path_parser_helpers import (
    _extract_all_document_file_paths,
    _extract_document_output_path,
    _extract_document_source_path,
    _extract_file_path,
)
from core.tasks.scheduler_core.pure_helpers import _strip_quotes


def _parse_goal_overrides(goal: str) -> Dict[str, Any]:
    text = str(goal or "").strip()
    segments = [seg.strip() for seg in text.split("::") if seg.strip()]

    clean_goal = segments[0] if segments else text
    depends_on: List[str] = []
    steps: List[Dict[str, Any]] = []

    for seg in segments[1:]:
        lower = seg.lower()

        if lower.startswith("depends_on="):
            dep_text = seg.split("=", 1)[1].strip()
            raw_deps = [x.strip() for x in dep_text.split(",") if x.strip()]
            seen = set()
            for dep in raw_deps:
                if dep not in seen:
                    seen.add(dep)
                    depends_on.append(dep)
            continue

        if lower.startswith("step="):
            step_value = seg.split("=", 1)[1].strip()
            parsed_step = _parse_inline_step(step_value)
            if isinstance(parsed_step, dict):
                steps.append(parsed_step)
            continue

    return {
        "clean_goal": clean_goal,
        "depends_on": depends_on,
        "steps": steps if steps else None,
        "document_payload": _extract_document_task_payload(clean_goal),
    }


def _extract_document_task_payload(goal: str) -> Optional[Dict[str, str]]:
    stripped = str(goal or "").strip()
    if not stripped:
        return None

    lowered = stripped.lower()
    all_paths = _extract_all_document_file_paths(stripped)

    action_keywords = [
        "action item",
        "action items",
        "extract action items",
        "todo",
        "to-do",
    ]
    summary_keywords = [
        "summary",
        "summarize",
        "summarise",
    ]

    wants_action_items = any(keyword in lowered for keyword in action_keywords)
    wants_summary = any(keyword in lowered for keyword in summary_keywords)

    if not wants_action_items and not wants_summary:
        output_hint = _extract_document_output_path(stripped, all_paths).lower()
        if "action_items" in output_hint or "action-items" in output_hint or "actionitems" in output_hint:
            wants_action_items = True
        elif "summary" in output_hint:
            wants_summary = True

    if not wants_action_items and not wants_summary:
        return None

    input_file = _extract_document_source_path(stripped, all_paths) or "input.txt"

    if wants_action_items:
        output_file = _extract_document_output_path(stripped, all_paths) or "action_items.txt"
        return {
            "task_type": "document",
            "mode": "action_items",
            "input_file": input_file,
            "output_file": output_file,
        }

    output_file = _extract_document_output_path(stripped, all_paths) or "summary.txt"
    return {
        "task_type": "document",
        "mode": "summary",
        "input_file": input_file,
        "output_file": output_file,
    }


def _parse_inline_step(text: str) -> Optional[Dict[str, Any]]:
    value = str(text or "").strip()
    if not value:
        return None

    lower = value.lower()

    if lower == "noop":
        return {"type": "noop", "message": "noop ok"}

    if lower.startswith("command:"):
        command = value.split(":", 1)[1].strip()
        if command:
            return {"type": "command", "command": command}
        return None

    if lower.startswith("run_python:"):
        path = value.split(":", 1)[1].strip()
        if path:
            return {"type": "run_python", "path": path}
        return None

    if lower.startswith("verify:"):
        payload = value.split(":", 1)[1].strip()
        if not payload:
            return None

        if payload.startswith("contains="):
            keyword = payload.split("=", 1)[1].strip()
            if keyword:
                return {"type": "verify", "contains": keyword}
            return None

        if payload.startswith("equals="):
            expected = payload.split("=", 1)[1]
            return {"type": "verify", "equals": expected}

        if payload.startswith("path="):
            path = payload.split("=", 1)[1].strip()
            if path:
                return {"type": "verify", "path": path}
            return None

        return {"type": "verify", "contains": payload}

    if lower.startswith("read_file:"):
        path = value.split(":", 1)[1].strip()
        if path:
            return {"type": "read_file", "path": path}
        return None

    if lower.startswith("ensure_file:"):
        path = value.split(":", 1)[1].strip()
        if path:
            return {"type": "ensure_file", "path": path}
        return None

    if lower.startswith("write_file:"):
        payload = value.split(":", 1)[1]
        if "|" in payload:
            path, content = payload.split("|", 1)
        else:
            path, content = payload, ""
        path = path.strip()
        if not path:
            return None
        return {
            "type": "write_file",
            "path": path,
            "content": content,
        }

    return None


def _looks_like_hello_world_python(text: str) -> bool:
    lowered = str(text or "").lower()
    candidates = [
        "hello world python",
        "hello world ??python",
        "python hello world",
    ]
    return any(item in lowered for item in candidates)


def _try_plan_write_file(text: str) -> Optional[Dict[str, Any]]:
    stripped = str(text or "").strip()
    lowered = stripped.lower()

    if not any(k in stripped for k in ["write", "create", "make"]) and not any(
        k in lowered for k in ["write", "create", "make"]
    ):
        return None

    path = _extract_file_path(stripped)
    if not path:
        return None

    content, has_explicit_content = _extract_write_content(stripped)
    if has_explicit_content:
        return {
            "type": "write_file",
            "path": path,
            "content": content,
        }

    return {
        "type": "ensure_file",
        "path": path,
    }


def _extract_write_content(text: str) -> Tuple[str, bool]:
    stripped = str(text or "").strip()

    patterns = [
        r"\bfix\s+(?:the\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+function\b",
        r"\brepair\s+(?:the\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+function\b",
        r"\bcorrect\s+(?:the\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+function\b",
        r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\b",
        r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    ]

    for pattern in patterns:
        m = re.search(pattern, stripped, flags=re.IGNORECASE)
        if m:
            value = m.group(1).strip()
            if value:
                return _strip_quotes(value), True

    return "", False


def _try_plan_read_file(text: str) -> Optional[Dict[str, Any]]:
    stripped = str(text or "").strip()

    m = re.search(r"([A-Za-z0-9_\-./\\]+\.(py|json|txt|md))", stripped, flags=re.IGNORECASE)
    if not m:
        return None

    path = m.group(1)
    lowered = stripped.lower()

    read_keywords = (
        "read",
        "open",
        "show",
        "cat",
        "查看",
    )

    if any(keyword in lowered for keyword in read_keywords):
        return {"type": "read_file", "path": path}

    return None
