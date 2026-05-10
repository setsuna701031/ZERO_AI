from __future__ import annotations

from typing import Any, Dict, List


def format_runtime_repair_envelope(envelope: Any) -> str:
    safe = envelope if isinstance(envelope, dict) else {}

    lines: List[str] = []

    lines.append("Runtime Repair Envelope:")

    _append(lines, "task_id", safe.get("task_id"))
    _append(lines, "status", safe.get("status"))
    _append(lines, "repair_mode", safe.get("repair_mode"))
    _append(lines, "repair_scope", safe.get("repair_scope"))
    _append(lines, "repair_risk", safe.get("repair_risk"))
    _append(lines, "suggestion_type", safe.get("suggestion_type"))
    _append(lines, "severity", safe.get("severity"))
    _append(lines, "retry_recommended", safe.get("retry_recommended"))
    _append(lines, "requires_confirmation", safe.get("requires_confirmation"))
    _append(lines, "max_retry", safe.get("max_retry"))

    reason = _safe_text(safe.get("reason"))
    if reason:
        lines.append(f"  - reason: {reason}")

    summary = _safe_text(safe.get("human_summary"))
    if summary:
        lines.append(f"  - summary: {summary}")

    allowed = _safe_list(safe.get("allowed_actions"))
    if allowed:
        lines.append("  - allowed_actions:")
        for item in allowed:
            lines.append(f"      - {item}")

    blocked = _safe_list(safe.get("blocked_actions"))
    if blocked:
        lines.append("  - blocked_actions:")
        for item in blocked:
            lines.append(f"      - {item}")

    inspect_targets = _safe_list(safe.get("inspection_targets"))
    if inspect_targets:
        lines.append("  - inspection_targets:")
        for item in inspect_targets:
            lines.append(f"      - {item}")

    return "\n".join(lines)


def _append(lines: List[str], key: str, value: Any) -> None:
    text = _safe_text(value)
    if text:
        lines.append(f"  - {key}: {text}")


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []

    result: List[str] = []

    for item in value:
        text = _safe_text(item)
        if text:
            result.append(text)

    return result