from __future__ import annotations

import copy

from typing import Any, Dict


def runtime_step_action_type(step: Any) -> str:
    if not isinstance(step, dict):
        return "unknown"
    return str(step.get("type") or step.get("action") or step.get("operation") or "unknown").strip().lower() or "unknown"


def runtime_step_target(step: Any) -> str:
    if not isinstance(step, dict):
        return ""
    for key in ("target", "target_path", "path", "file_path", "output_path", "summary_output_path", "action_items_output_path", "command", "cmd"):
        value = step.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def runtime_step_id(step: Any, step_index: int) -> str:
    if isinstance(step, dict):
        for key in ("id", "step_id", "name"):
            value = step.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return "step_" + str(int(step_index))


def runtime_action_id(task: Dict[str, Any], step: Any, step_index: int) -> str:
    task_id = str(task.get("task_id") or task.get("id") or task.get("task_name") or "task").strip()
    return "action_" + task_id + "_" + runtime_step_id(step, step_index) + "_" + runtime_step_action_type(step)


def runtime_linked_session_node(task: Dict[str, Any], step: Any, step_index: int) -> str:
    if isinstance(step, dict):
        for key in ("linked_session_node", "session_node", "node_id", "repair_session_node"):
            value = step.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    repair_context = task.get("repair_context") if isinstance(task, dict) else {}
    if isinstance(repair_context, dict):
        repair_session = repair_context.get("repair_session")
        if isinstance(repair_session, dict):
            session_id = str(repair_session.get("session_id") or repair_session.get("id") or "").strip()
            if session_id:
                return session_id + ":step_" + str(int(step_index))
    return ""


def runtime_action_metadata(step: Any, step_index: int, current_tick: int, trace_tick: int) -> Dict[str, Any]:
    return {
        "step_index": int(step_index),
        "current_tick": current_tick,
        "trace_tick": trace_tick,
        "step": copy.deepcopy(step) if isinstance(step, dict) else {},
    }