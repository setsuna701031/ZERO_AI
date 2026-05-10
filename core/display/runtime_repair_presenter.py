from __future__ import annotations

from typing import Any, Mapping

from core.tasks.runtime_repair_suggestion import build_runtime_repair_suggestion


SUMMARY_FIELD_LIMIT = 220


def format_runtime_repair_suggestion(suggestion_or_snapshot: Any) -> str:
    """Render a read-only runtime repair suggestion for CLI/operator output.

    Accepts either a prebuilt suggestion dictionary or a runtime replay snapshot.
    This presenter is display-only: it does not schedule repair tasks, mutate
    runtime state, call tools, or write files.
    """
    suggestion = _ensure_suggestion(suggestion_or_snapshot)
    inspection = _list_or_empty(suggestion.get("recommended_inspection"))

    lines = [
        "Runtime Repair Suggestion:",
        f"- task_id: {_display(suggestion.get('task_id'))}",
        f"- status: {_display(suggestion.get('status'))}",
        f"- type: {_display(suggestion.get('suggestion_type'))}",
        f"- severity: {_display(suggestion.get('severity'))}",
        f"- retry_recommended: {_bool_text(suggestion.get('retry_recommended'))}",
        f"- reason: {_display(suggestion.get('reason'), SUMMARY_FIELD_LIMIT)}",
    ]

    failed_event = suggestion.get("failed_event")
    if isinstance(failed_event, Mapping):
        lines.append(f"- failed_event: {_display(_format_failed_event(failed_event), SUMMARY_FIELD_LIMIT)}")

    if inspection:
        lines.append("- inspect:")
        for item in inspection:
            text = _safe_str(item)
            if text:
                lines.append(f"  - {text}")
    else:
        lines.append("- inspect: <none>")

    lines.append(f"- summary: {_display(suggestion.get('human_summary'), SUMMARY_FIELD_LIMIT)}")
    return "\n".join(lines)


def format_runtime_repair_suggestions(snapshot: Any) -> str:
    """Plural wrapper for future multi-suggestion flows."""
    return format_runtime_repair_suggestion(snapshot)


def _ensure_suggestion(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping) and "suggestion_type" in value:
        return dict(value)
    suggestion = build_runtime_repair_suggestion(value)
    return dict(suggestion) if isinstance(suggestion, Mapping) else {}


def _format_failed_event(event: Mapping[str, Any]) -> str:
    parts = []
    for key in ("action_type", "status", "error_type", "message", "classification", "attempts"):
        value = _safe_str(event.get(key))
        if value:
            parts.append(f"{key}={value}")
    return "; ".join(parts)


def _bool_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return _display(value)


def _list_or_empty(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    return []


def _display(value: Any, max_len: int = SUMMARY_FIELD_LIMIT) -> str:
    text = _compact_text(value, max_len=max_len)
    return text if text else "<none>"


def _compact_text(value: Any, max_len: int = SUMMARY_FIELD_LIMIT) -> str:
    text = _safe_str(value)
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
