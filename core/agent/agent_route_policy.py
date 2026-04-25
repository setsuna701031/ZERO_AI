from __future__ import annotations

import re
from typing import Any, Dict


DOCUMENT_PATH_PATTERN = re.compile(
    r"[a-z0-9_\-./\\]+\.(txt|md|log|json|csv|yaml|yml)\b"
)


def should_force_planner_document_flow(user_input: str) -> bool:
    text = str(user_input or "").strip().lower()
    if not text:
        return False

    if looks_like_summary_document_flow(text):
        return True

    if looks_like_action_items_document_flow(text):
        return True

    return False


def looks_like_summary_document_flow(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False

    summary_keywords = ["summary", "summarize", "summarise", "摘要", "總結"]
    has_summary = any(keyword in normalized for keyword in summary_keywords)
    has_doc_path = has_document_path(normalized)
    return has_summary and has_doc_path


def looks_like_action_items_document_flow(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False

    action_keywords = ["action item", "action items", "待辦事項", "行動項目", "todo", "to-do"]
    has_action = any(keyword in normalized for keyword in action_keywords)
    has_doc_path = has_document_path(normalized)
    return has_action and has_doc_path


def has_document_path(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    return bool(DOCUMENT_PATH_PATTERN.search(normalized))


def detect_document_flow_capability(user_input: str) -> Dict[str, Any]:
    """
    Detect document-flow capability intent without executing anything.

    This helper is intentionally policy-only. It does not call tools, does not
    run tasks, and does not replace AgentLoop planning. Future AgentLoop or
    planner code can use this as a small signal when deciding whether to call
    a capability wrapper such as core.capabilities.document_flow_orchestrator.

    Return shape when matched:
    {
        "matched": True,
        "capability": "document_flow",
        "operation": "summary" | "action_items" | "summary_and_action_items",
        "reason": "...",
    }

    Return shape when not matched:
    {
        "matched": False,
        "capability": "",
        "operation": "",
        "reason": "...",
    }
    """
    normalized = str(user_input or "").strip().lower()
    if not normalized:
        return {
            "matched": False,
            "capability": "",
            "operation": "",
            "reason": "empty_input",
        }

    if not has_document_path(normalized):
        return {
            "matched": False,
            "capability": "",
            "operation": "",
            "reason": "no_document_path",
        }

    wants_summary = looks_like_summary_document_flow(normalized)
    wants_action_items = looks_like_action_items_document_flow(normalized)

    if wants_summary and wants_action_items:
        return {
            "matched": True,
            "capability": "document_flow",
            "operation": "summary_and_action_items",
            "reason": "summary_and_action_items_document_flow",
        }

    if wants_summary:
        return {
            "matched": True,
            "capability": "document_flow",
            "operation": "summary",
            "reason": "summary_document_flow",
        }

    if wants_action_items:
        return {
            "matched": True,
            "capability": "document_flow",
            "operation": "action_items",
            "reason": "action_items_document_flow",
        }

    return {
        "matched": False,
        "capability": "",
        "operation": "",
        "reason": "document_path_without_supported_operation",
    }


def looks_like_explicit_task_request(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False

    explicit_patterns = [
        r"^\s*task\s+",
        r"\bcreate task\b",
        r"\bnew task\b",
        r"\bsubmit task\b",
        r"\bschedule\b",
        r"\bqueue\b",
        r"\bbackground\b",
        r"\blong[- ]running\b",
        r"\brun in background\b",
        r"\benqueue\b",
        r"建立任務",
        r"新增任務",
        r"提交任務",
        r"排程",
        r"加入佇列",
        r"背景執行",
        r"長任務",
    ]

    return any(re.search(pattern, normalized) for pattern in explicit_patterns)


def should_enter_task_mode(route: Any, user_input: str) -> bool:
    if isinstance(route, dict):
        if route.get("mode") == "task":
            return True
        if route.get("type") == "task":
            return True
        if route.get("task") is True:
            return True
        if route.get("long_running") is True:
            return True

        route_intent = str(route.get("intent") or "").strip().lower()
        if route_intent in {"task", "task_execution", "agent_task"}:
            return True

        route_action = str(route.get("action") or "").strip().lower()
        if route_action in {"create_task", "submit_task", "background_task"}:
            return True

    return looks_like_explicit_task_request(user_input)
