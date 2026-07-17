from __future__ import annotations

import copy
import json
from typing import Any, Dict, List


def safe_public_results_summary(results: Any, *, max_items: int = 3) -> List[Dict[str, Any]]:
    """Build a compact public-safe results summary."""
    if not isinstance(results, list):
        return []

    summary: List[Dict[str, Any]] = []
    for item in results[-max_items:]:
        if not isinstance(item, dict):
            continue

        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        error = result.get("error") if isinstance(result.get("error"), dict) else {}

        step = item.get("step") if isinstance(item.get("step"), dict) else {}
        if not step and isinstance(result.get("step"), dict):
            step = result.get("step")

        error_type = (
            result.get("error_type")
            or error.get("type")
            or item.get("error_type")
            or item.get("failure_type")
            or ""
        )
        message = (
            result.get("message")
            or result.get("final_answer")
            or error.get("message")
            or item.get("message")
            or item.get("final_answer")
            or item.get("last_error")
            or item.get("failure_message")
            or ""
        )

        entry = {
            "step_index": item.get("step_index"),
            "step_type": (
                result.get("step_type")
                or item.get("step_type")
                or step.get("type")
                or step.get("action")
                or ""
            ),
            "ok": bool(result.get("ok", item.get("ok", False))),
            "blocked": bool(result.get("blocked", item.get("blocked", False))),
            "failed": bool(result.get("failed", item.get("failed", False))),
            "error_type": str(error_type)[:200],
            "message": str(message)[:500],
        }

        metadata = item.get("metadata")
        if isinstance(metadata, dict):
            compact_metadata: Dict[str, Any] = {}
            for key in (
                "error_type",
                "approval_state",
                "approval_status",
                "approval_required",
                "requires_approval",
                "requires_review",
                "blocked_reason",
                "reason",
            ):
                if key in metadata:
                    value = metadata.get(key)
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        compact_metadata[key] = value
                    else:
                        compact_metadata[key] = str(value)[:500]
            if compact_metadata:
                entry["metadata"] = compact_metadata

        summary.append(entry)

    return summary


def safe_task_for_snapshot(task: Any) -> Dict[str, Any]:
    """Return a bounded task payload for public snapshot / result persistence."""
    if not isinstance(task, dict):
        return {}

    sanitized: Dict[str, Any] = {}
    shallow_keys = [
        "task_id",
        "task_name",
        "id",
        "title",
        "goal",
        "status",
        "priority",
        "task_type",
        "created_tick",
        "last_run_tick",
        "finished_tick",
        "last_failure_tick",
        "last_error",
        "failure_type",
        "failure_message",
        "current_step_index",
        "steps_total",
        "retry_count",
        "max_retries",
        "retry_delay",
        "next_retry_tick",
        "timeout_ticks",
        "wait_until_tick",
        "workspace_root",
        "workspace_dir",
        "shared_dir",
        "task_dir",
        "sandbox_dir",
        "plan_file",
        "runtime_state_file",
        "result_file",
        "execution_log_file",
        "snapshot_file",
        "log_file",
        "scheduler_build",
        "final_answer",
        "summary",
        "requires_approval",
        "requires_review",
        "review_status",
        "review_id",
        "blocked_reason",
        "waiting_reason",
        "next_action",
    ]

    for key in shallow_keys:
        if key in task:
            value = task.get(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                sanitized[key] = value
            else:
                sanitized[key] = str(value)[:1000]

    steps = task.get("steps")
    if isinstance(steps, list):
        sanitized["steps"] = [_compact_step(item) for item in steps if isinstance(item, dict)]
    else:
        sanitized["steps"] = []

    history = task.get("history")
    sanitized["history"] = list(history[-20:]) if isinstance(history, list) else []
    sanitized["results"] = safe_public_results_summary(task.get("results", []), max_items=5)
    sanitized["step_results"] = safe_public_results_summary(task.get("step_results", []), max_items=5)

    last_step = task.get("last_step_result")
    if isinstance(last_step, dict):
        compact_last_step = safe_public_results_summary([last_step], max_items=1)
        sanitized["last_step_result"] = compact_last_step[0] if compact_last_step else {}
    else:
        sanitized["last_step_result"] = None

    execution_log = task.get("execution_log")
    if isinstance(execution_log, list):
        sanitized["execution_log"] = safe_public_results_summary(execution_log, max_items=20)
    else:
        sanitized["execution_log"] = []

    planner_result = task.get("planner_result")
    if isinstance(planner_result, dict):
        sanitized["planner_result"] = {
            "intent": str(planner_result.get("intent") or ""),
            "summary": str(planner_result.get("summary") or "")[:1000],
            "steps_total": len(planner_result.get("steps", [])) if isinstance(planner_result.get("steps"), list) else 0,
        }

    public_snapshot = task.get("public_snapshot")
    if isinstance(public_snapshot, dict):
        sanitized["public_snapshot"] = {
            "task_id": str(public_snapshot.get("task_id") or sanitized.get("task_id") or ""),
            "status": str(public_snapshot.get("status") or sanitized.get("status") or ""),
            "final_answer": str(public_snapshot.get("final_answer") or sanitized.get("final_answer") or "")[:1000],
        }

    return sanitized


def _compact_step(item: dict[str, Any]) -> dict[str, Any]:
    compact_step: Dict[str, Any] = {}
    for key, value in item.items():
        clean_key = str(key or "").strip()
        if not clean_key:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            compact_step[clean_key] = value
            continue
        if isinstance(value, (dict, list)):
            try:
                json.dumps(value, ensure_ascii=False)
                compact_step[clean_key] = copy.deepcopy(value)
            except Exception:
                compact_step[clean_key] = str(value)[:1000]
            continue
        compact_step[clean_key] = str(value)[:1000]
    return compact_step


__all__ = [
    "safe_public_results_summary",
    "safe_task_for_snapshot",
]
