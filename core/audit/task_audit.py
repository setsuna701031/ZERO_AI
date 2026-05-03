from __future__ import annotations

import copy
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


AUDIT_EVENT_FIELDS = (
    "audit_id",
    "task_id",
    "trace_id",
    "event_type",
    "timestamp",
    "source",
    "actor",
    "goal",
    "status",
    "policy_hint",
    "policy_decision",
    "policy_reason",
    "policy_source",
    "execution_status",
    "tool_name",
    "target_path",
    "result_summary",
    "error",
    "metadata",
)

MAX_SUMMARY_CHARS = 240
MAX_ERROR_CHARS = 500
MAX_METADATA_TEXT_CHARS = 1000
MAX_METADATA_ITEMS = 25


def resolve_audit_log_path(workspace_root: str) -> str:
    root = os.path.abspath(workspace_root or "workspace")
    return os.path.join(root, "audit", "task_audit.jsonl")


def build_audit_event(
    *,
    task: Optional[Dict[str, Any]] = None,
    event_type: str,
    trace_id: str = "",
    source: str = "",
    actor: str = "zero",
    goal: str = "",
    status: str = "",
    policy_hint: Any = None,
    policy_decision: Any = None,
    policy_reason: str = "",
    policy_source: str = "",
    execution_status: str = "",
    tool_name: str = "",
    target_path: str = "",
    result_summary: str = "",
    error: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    task_payload = task if isinstance(task, dict) else {}
    task_id = _first_text(task_payload.get("task_id"), task_payload.get("task_name"), task_payload.get("id"))
    resolved_source = normalize_task_source(_first_text(source, task_payload.get("source")))
    resolved_goal = _short_text(_first_text(goal, task_payload.get("goal"), task_payload.get("title")), MAX_SUMMARY_CHARS)
    resolved_status = _first_text(status, task_payload.get("status"), "unknown")

    event = {
        "audit_id": uuid.uuid4().hex,
        "task_id": task_id or "unknown_task",
        "trace_id": _first_text(trace_id, task_payload.get("trace_id"), task_payload.get("trace_file")),
        "event_type": str(event_type or "unknown").strip() or "unknown",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": resolved_source,
        "actor": _first_text(actor, task_payload.get("actor"), "zero"),
        "goal": resolved_goal,
        "status": resolved_status,
        "policy_hint": _json_safe(policy_hint if policy_hint is not None else task_payload.get("policy_hint")),
        "policy_decision": _normalize_policy_decision_value(
            policy_decision if policy_decision is not None else task_payload.get("policy_decision")
        ),
        "policy_reason": _short_text(_first_text(policy_reason, task_payload.get("policy_reason")), MAX_SUMMARY_CHARS),
        "policy_source": _short_text(_first_text(policy_source, task_payload.get("policy_source")), MAX_SUMMARY_CHARS),
        "execution_status": _short_text(_first_text(execution_status), MAX_SUMMARY_CHARS),
        "tool_name": _short_text(_first_text(tool_name), MAX_SUMMARY_CHARS),
        "target_path": _short_text(_first_text(target_path), MAX_SUMMARY_CHARS),
        "result_summary": _short_text(_first_text(result_summary), MAX_SUMMARY_CHARS),
        "error": _short_text(_first_text(error), MAX_ERROR_CHARS),
        "metadata": _json_safe(metadata if isinstance(metadata, dict) else {}),
    }

    for field in AUDIT_EVENT_FIELDS:
        event.setdefault(field, None)
    return {field: event.get(field) for field in AUDIT_EVENT_FIELDS}


def write_audit_event(workspace_root: str, event: Dict[str, Any]) -> bool:
    try:
        if not isinstance(event, dict):
            return False
        path = resolve_audit_log_path(workspace_root)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        safe_event = {field: _json_safe(event.get(field)) for field in AUDIT_EVENT_FIELDS}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe_event, ensure_ascii=False, separators=(",", ":")) + "\n")
        return True
    except Exception:
        return False


def load_audit_events(workspace_root: str, task_id: str = "") -> List[Dict[str, Any]]:
    path = resolve_audit_log_path(workspace_root)
    if not os.path.exists(path):
        return []

    events: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                try:
                    event = json.loads(text)
                except Exception:
                    continue
                if not isinstance(event, dict):
                    continue
                if task_id and str(event.get("task_id") or "") != str(task_id):
                    continue
                events.append(event)
    except Exception:
        return []
    return events


def normalize_task_source(value: Any) -> str:
    source = str(value or "").strip().lower()
    aliases = {
        "command": "cli",
        "terminal": "cli",
        "ui": "app",
        "web": "app",
        "l5_world_trigger": "scheduler",
    }
    source = aliases.get(source, source)
    if source in {"cli", "app", "scheduler", "test", "system"}:
        return source
    return "unknown"


def _normalize_policy_decision_value(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("decision")
    decision = str(value or "").strip().lower()
    if decision in {"allow", "deny", "require_confirm", "unknown"}:
        return decision
    if decision in {"allowed", "ok", "pass"}:
        return "allow"
    if decision in {"blocked", "denied", "fail"}:
        return "deny"
    return "unknown"


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _short_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _json_safe(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "<truncated>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _short_text(value, MAX_METADATA_TEXT_CHARS)
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, list):
        return [_json_safe(item, depth + 1) for item in value[:MAX_METADATA_ITEMS]]
    if isinstance(value, dict):
        safe: Dict[str, Any] = {}
        for key, item in list(value.items())[:MAX_METADATA_ITEMS]:
            safe[str(key)] = _json_safe(item, depth + 1)
        return safe
    if isinstance(value, (datetime,)):
        return value.isoformat()
    try:
        json.dumps(value)
        return value
    except Exception:
        return _short_text(str(value), MAX_METADATA_TEXT_CHARS)
