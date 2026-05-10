from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from core.planning.planner_contract_trace import (
    load_planner_contract_trace,
    summarize_planner_contract_trace,
)
from core.tasks.execution_contract_trace import (
    load_execution_contract_trace,
    summarize_execution_contract_trace,
)
from core.tasks.runtime_kernel_events import (
    normalize_runtime_kernel_events,
    summarize_normalized_kernel_events,
)
from core.tasks.runtime_kernel_timeline import (
    build_runtime_timeline,
    summarize_runtime_timeline,
)


RUNTIME_KERNEL_STATUS_VERSION = "runtime_kernel_status.v1"


def build_runtime_kernel_status(
    *,
    planner_trace_path: Optional[Any] = None,
    execution_trace_path: Optional[Any] = None,
    limit: int = 200,
) -> Dict[str, Any]:
    planner_events = load_planner_contract_trace(
        trace_path=planner_trace_path,
        limit=limit,
    )
    execution_events = load_execution_contract_trace(
        trace_path=execution_trace_path,
        limit=limit,
    )

    return build_runtime_kernel_status_from_events(
        planner_events=planner_events,
        execution_events=execution_events,
    )


def build_runtime_kernel_status_from_events(
    *,
    planner_events: Any = None,
    execution_events: Any = None,
) -> Dict[str, Any]:
    planner_events = planner_events if isinstance(planner_events, list) else []
    execution_events = execution_events if isinstance(execution_events, list) else []

    planner_summary = summarize_planner_contract_trace(planner_events)
    execution_summary = summarize_execution_contract_trace(execution_events)
    normalized_events = normalize_runtime_kernel_events(
        planner_events,
        source="planner",
    ) + normalize_runtime_kernel_events(
        execution_events,
        source="execution",
    )
    timeline = build_runtime_timeline(normalized_events)

    return {
        "ok": bool(planner_summary.get("ok", False)) and bool(execution_summary.get("ok", False)),
        "version": RUNTIME_KERNEL_STATUS_VERSION,
        "planner": planner_summary,
        "execution": execution_summary,
        "events": summarize_normalized_kernel_events(normalized_events),
        "timeline": summarize_runtime_timeline(timeline),
        "kernel": _build_kernel_summary(
            planner_summary=planner_summary,
            execution_summary=execution_summary,
        ),
    }


def _build_kernel_summary(
    *,
    planner_summary: Dict[str, Any],
    execution_summary: Dict[str, Any],
) -> Dict[str, Any]:
    planner_events = int(planner_summary.get("event_count", 0) or 0)
    execution_events = int(execution_summary.get("event_count", 0) or 0)

    planner_invalid = int(planner_summary.get("invalid_count", 0) or 0)
    execution_invalid = int(execution_summary.get("invalid_count", 0) or 0)

    planner_noop = int(planner_summary.get("noop_count", 0) or 0)
    execution_noop = int(execution_summary.get("noop_count", 0) or 0)

    planner_errors = int(planner_summary.get("error_count", 0) or 0)
    execution_errors = int(execution_summary.get("error_count", 0) or 0)

    planner_warnings = int(planner_summary.get("warning_count", 0) or 0)
    execution_warnings = int(execution_summary.get("warning_count", 0) or 0)

    total_events = planner_events + execution_events
    total_invalid = planner_invalid + execution_invalid
    total_noop = planner_noop + execution_noop
    total_errors = planner_errors + execution_errors
    total_warnings = planner_warnings + execution_warnings

    return {
        "status": _classify_kernel_status(
            total_events=total_events,
            total_invalid=total_invalid,
            total_errors=total_errors,
        ),
        "total_events": total_events,
        "total_invalid": total_invalid,
        "total_noop": total_noop,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "planner_event_count": planner_events,
        "execution_event_count": execution_events,
        "planner_ready": planner_events >= 0 and bool(planner_summary.get("ok", False)),
        "execution_ready": execution_events >= 0 and bool(execution_summary.get("ok", False)),
    }


def _classify_kernel_status(
    *,
    total_events: int,
    total_invalid: int,
    total_errors: int,
) -> str:
    if total_events <= 0:
        return "no_trace"

    if total_errors > 0 or total_invalid > 0:
        return "attention_required"

    return "healthy"


def format_runtime_kernel_status(status: Dict[str, Any]) -> str:
    if not isinstance(status, dict):
        return "runtime kernel status unavailable"

    kernel = status.get("kernel") if isinstance(status.get("kernel"), dict) else {}
    planner = status.get("planner") if isinstance(status.get("planner"), dict) else {}
    execution = status.get("execution") if isinstance(status.get("execution"), dict) else {}

    return (
        f"Runtime Kernel Status: {kernel.get('status', 'unknown')}\n"
        f"- planner events: {planner.get('event_count', 0)}\n"
        f"- execution events: {execution.get('event_count', 0)}\n"
        f"- total invalid: {kernel.get('total_invalid', 0)}\n"
        f"- total errors: {kernel.get('total_errors', 0)}\n"
        f"- total warnings: {kernel.get('total_warnings', 0)}"
    )


def build_task_runtime_kernel_status(
    task: Mapping[str, Any],
    *,
    planner_trace_path: Optional[Any] = None,
    execution_trace_path: Optional[Any] = None,
    limit: int = 200,
) -> Dict[str, Any]:
    """Build display-only kernel status enriched with task runtime context."""
    safe_task = task if isinstance(task, Mapping) else {}
    status = build_runtime_kernel_status(
        planner_trace_path=planner_trace_path,
        execution_trace_path=execution_trace_path,
        limit=limit,
    )
    status["task"] = {
        "task_id": _first_nonempty(safe_task.get("task_id"), safe_task.get("task_name"), safe_task.get("id")),
        "status": _first_nonempty(safe_task.get("status"), "unknown"),
        "blocked_reason": _extract_blocked_reason(safe_task),
        "unresolved_blockers": _extract_unresolved_blockers(safe_task),
        "latest_runtime_step": _extract_latest_runtime_step(safe_task),
    }
    return status


def format_task_runtime_kernel_status(status: Dict[str, Any]) -> str:
    if not isinstance(status, dict):
        return "runtime kernel summary unavailable"

    kernel_text = format_runtime_kernel_status(status)
    task = status.get("task") if isinstance(status.get("task"), dict) else {}
    blocked_reason = str(task.get("blocked_reason") or "").strip()
    blockers = task.get("unresolved_blockers")
    if not isinstance(blockers, list):
        blockers = []
    latest_step = str(task.get("latest_runtime_step") or "").strip()

    lines = [kernel_text]
    lines.append(f"- unresolved blockers: {len(blockers)}")
    if blocked_reason:
        lines.append(f"- blocked reason: {blocked_reason}")
    elif blockers:
        lines.append(f"- blocked reason: {blockers[0]}")
    else:
        lines.append("- blocked reason: none")
    lines.append(f"- latest runtime step: {latest_step or 'none'}")
    return "\n".join(lines)


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _extract_blocked_reason(task: Mapping[str, Any]) -> str:
    status = str(task.get("status") or "").strip().lower()
    if status != "blocked":
        return ""
    return _first_nonempty(
        task.get("blocked_reason"),
        task.get("failure_message"),
        task.get("last_error"),
        task.get("error"),
    )


def _extract_unresolved_blockers(task: Mapping[str, Any]) -> List[str]:
    blockers: List[str] = []
    for key in ("unresolved_blockers", "active_blockers", "blockers"):
        value = task.get(key)
        if isinstance(value, list):
            for item in value:
                text = _blocker_text(item)
                if text:
                    blockers.append(text)
        else:
            text = _blocker_text(value)
            if text:
                blockers.append(text)

    blocked_reason = _extract_blocked_reason(task)
    if blocked_reason:
        blockers.append(blocked_reason)

    seen = set()
    unique: List[str] = []
    for blocker in blockers:
        if blocker in seen:
            continue
        seen.add(blocker)
        unique.append(blocker)
    return unique


def _blocker_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return _first_nonempty(
            value.get("reason"),
            value.get("blocked_reason"),
            value.get("message"),
            value.get("error"),
            value.get("type"),
        )
    return ""


def _extract_latest_runtime_step(task: Mapping[str, Any]) -> str:
    for key in ("current_step", "last_step", "latest_runtime_step"):
        text = _step_text(task.get(key))
        if text:
            return text

    for key in ("last_step_result", "last_result"):
        value = task.get(key)
        if isinstance(value, Mapping):
            text = _step_text(value.get("step")) or _first_nonempty(
                value.get("step_title"),
                value.get("step_name"),
                value.get("action"),
                value.get("type"),
            )
            if text:
                return text

    for key in ("execution_trace", "execution_log", "step_results", "results"):
        value = task.get(key)
        if isinstance(value, list):
            for item in reversed(value):
                text = _step_text(item)
                if text:
                    return text

    steps = task.get("steps")
    if isinstance(steps, list) and steps:
        index = _safe_int(task.get("current_step_index"), 0)
        if index >= len(steps):
            index = len(steps) - 1
        if index < 0:
            index = 0
        return _step_text(steps[index])

    return ""


def _step_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        nested = value.get("step")
        nested_text = _step_text(nested)
        if nested_text:
            return nested_text
        return _first_nonempty(
            value.get("title"),
            value.get("name"),
            value.get("description"),
            value.get("goal"),
            value.get("prompt"),
            value.get("action"),
            value.get("type"),
            value.get("event"),
            value.get("event_type"),
        )
    return ""


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default
