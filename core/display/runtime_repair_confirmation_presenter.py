from __future__ import annotations

from typing import Any, List, Mapping


def format_runtime_repair_confirmation_gate(gate: Any) -> str:
    """Render a read-only runtime repair confirmation gate for CLI output."""
    safe = gate if isinstance(gate, Mapping) else {}

    lines: List[str] = ["Runtime Repair Confirmation Gate:"]

    _append(lines, "task_id", safe.get("task_id"))
    _append(lines, "proposal_id", safe.get("proposal_id"))
    _append(lines, "proposal_type", safe.get("proposal_type"))
    _append(lines, "confirmation_status", safe.get("confirmation_status"))
    _append(lines, "requires_confirmation", safe.get("requires_confirmation"))
    _append(lines, "proposal_allowed", safe.get("proposal_allowed"))
    _append(lines, "planner_allowed_before_confirmation", safe.get("planner_allowed_before_confirmation"))
    _append(lines, "planner_allowed_after_confirmation", safe.get("planner_allowed_after_confirmation"))
    _append(lines, "mutation_allowed_after_confirmation", safe.get("mutation_allowed_after_confirmation"))
    _append(lines, "execution_allowed_after_confirmation", safe.get("execution_allowed_after_confirmation"))
    _append(lines, "allowed_next_action", safe.get("allowed_next_action"))
    _append(lines, "operator", safe.get("operator"))

    reason = _safe_text(safe.get("reason"))
    if reason:
        lines.append(f"  - reason: {reason}")

    required_fields = _safe_list(safe.get("confirmation_required_fields"))
    if required_fields:
        lines.append("  - confirmation_required_fields:")
        for item in required_fields:
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
