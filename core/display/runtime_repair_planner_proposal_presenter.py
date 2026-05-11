from __future__ import annotations

from typing import Any, List, Mapping


def format_runtime_repair_planner_proposal(proposal: Any) -> str:
    """Render a read-only runtime repair planner proposal payload for CLI output."""
    safe = proposal if isinstance(proposal, Mapping) else {}
    intent = safe.get("repair_intent") if isinstance(safe.get("repair_intent"), Mapping) else {}

    lines: List[str] = ["Runtime Repair Planner Proposal:"]

    _append(lines, "task_id", safe.get("task_id"))
    _append(lines, "status", safe.get("status"))
    _append(lines, "proposal_type", safe.get("proposal_type"))
    _append(lines, "proposal_mode", safe.get("proposal_mode"))
    _append(lines, "proposal_allowed", safe.get("proposal_allowed"))
    _append(lines, "planner_allowed", safe.get("planner_allowed"))
    _append(lines, "requires_confirmation", safe.get("requires_confirmation"))

    reason = _safe_text(safe.get("reason"))
    if reason:
        lines.append(f"  - reason: {reason}")

    summary = _safe_text(safe.get("human_summary"))
    if summary:
        lines.append(f"  - summary: {summary}")

    if intent:
        lines.append("  - repair_intent:")
        _append(lines, "intent_type", intent.get("intent_type"), indent="      ")
        _append(lines, "source", intent.get("source"), indent="      ")
        _append(lines, "scope", intent.get("scope"), indent="      ")
        _append(lines, "risk", intent.get("risk"), indent="      ")
        _append(lines, "mode", intent.get("mode"), indent="      ")
        _append(lines, "mutation_allowed", intent.get("mutation_allowed"), indent="      ")
        _append(lines, "execution_allowed", intent.get("execution_allowed"), indent="      ")

    _append_list(lines, "proposed_actions", safe.get("proposed_actions"))
    _append_list(lines, "blocked_actions", safe.get("blocked_actions"))
    _append_list(lines, "inspection_targets", safe.get("inspection_targets"))

    return "\n".join(lines)


def _append(lines: List[str], key: str, value: Any, *, indent: str = "  ") -> None:
    text = _safe_text(value)
    if text:
        lines.append(f"{indent}- {key}: {text}")


def _append_list(lines: List[str], key: str, value: Any, *, indent: str = "  ") -> None:
    items = _safe_list(value)
    if not items:
        return
    lines.append(f"{indent}- {key}:")
    for item in items:
        lines.append(f"{indent}    - {item}")


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
