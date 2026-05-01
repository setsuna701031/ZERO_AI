from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from core.events.event_schema import EventRecord


def event_to_task(event: EventRecord) -> Dict[str, Any]:
    filename = Path(event.path).name
    payload = _summarize_payload(event.payload)
    task_type = _task_type_for_event(filename, payload)
    title = _task_title_for_event(filename, payload, task_type)
    return {
        "id": f"event_{event.event_id}",
        "type": task_type,
        "title": title,
        "content": title,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "source": event.source,
        "source_path": event.path,
        "event_payload": payload,
    }


def _summarize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for key, value in list((payload or {}).items())[:12]:
        if isinstance(value, str) and len(value) > 200:
            summary[key] = f"{value[:200]}... <truncated len={len(value)}>"
        elif isinstance(value, (dict, list)):
            summary[key] = value
        else:
            summary[key] = value
    return summary


def _task_type_for_event(filename: str, payload: Dict[str, Any]) -> str:
    text = f"{filename} {payload.get('text_preview', '')}".lower()
    if any(keyword in text for keyword in ("fix", "bug", "scheduler", "commit", "publish", "pull request")):
        return "github_outbox"
    return "github_inbox"


def _task_title_for_event(filename: str, payload: Dict[str, Any], task_type: str) -> str:
    preview = str(payload.get("text_preview") or "").strip()
    if task_type == "github_outbox":
        task_text = preview.splitlines()[0].strip() if preview else filename
        return f"generate commit message for file event: {task_text}"
    return f"review/analyze file event: {filename}"
