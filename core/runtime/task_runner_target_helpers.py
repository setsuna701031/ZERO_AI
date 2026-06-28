from __future__ import annotations

import copy
import os
from datetime import datetime
from typing import Any, Callable, Dict, Optional


OperatorSessionResolver = Callable[..., str]


def normalize_target_repo_root(value: Any) -> str:
    text = str(value or "").strip().strip('"').strip("'")
    if not text:
        return ""
    text = os.path.expandvars(os.path.expanduser(text))
    try:
        text = os.path.abspath(text)
    except Exception:
        pass
    if os.path.isdir(text):
        return os.path.normpath(text)
    return ""


def extract_target_repo_root_from_mapping(value: Any) -> str:
    if not isinstance(value, dict):
        return ""

    for key in (
        "target_repo_root",
        "target_root",
        "repo_root",
        "project_root",
        "working_root",
        "workspace_target_root",
    ):
        resolved = normalize_target_repo_root(value.get(key))
        if resolved:
            return resolved

    for nested_key in ("config", "runtime_config", "engineering_config", "capability_execution"):
        nested = value.get(nested_key)
        if isinstance(nested, dict):
            resolved = extract_target_repo_root_from_mapping(nested)
            if resolved:
                return resolved

    repair_context = value.get("repair_context")
    if isinstance(repair_context, dict):
        resolved = normalize_target_repo_root(repair_context.get("target_repo_root"))
        if resolved:
            return resolved
        engineering_execution = repair_context.get("engineering_execution")
        if isinstance(engineering_execution, dict):
            resolved = normalize_target_repo_root(engineering_execution.get("target_repo_root"))
            if resolved:
                return resolved

    return ""


def resolve_target_repo_root(
    task: Dict[str, Any],
    state: Optional[Dict[str, Any]] = None,
) -> str:
    resolved = extract_target_repo_root_from_mapping(task)
    if resolved:
        return resolved

    resolved = extract_target_repo_root_from_mapping(state)
    if resolved:
        return resolved

    resolved = normalize_target_repo_root(os.environ.get("ZERO_TARGET_REPO_ROOT"))
    if resolved:
        return resolved

    return ""


def sync_target_repo_context(task: Dict[str, Any], state: Dict[str, Any]) -> str:
    target_repo_root = resolve_target_repo_root(task=task, state=state)
    if not target_repo_root:
        return ""

    if isinstance(task, dict):
        task["target_repo_root"] = target_repo_root

    if isinstance(state, dict):
        state["target_repo_root"] = target_repo_root
        repair_context = state.setdefault("repair_context", {})
        if isinstance(repair_context, dict):
            repair_context["target_repo_root"] = target_repo_root
            engineering_execution = repair_context.setdefault("engineering_execution", {})
            if isinstance(engineering_execution, dict):
                engineering_execution["target_repo_root"] = target_repo_root
                engineering_execution["target_routing_version"] = "aer_v9_2_0"
                engineering_execution["last_target_routing_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return target_repo_root


def resolve_step_cwd(
    *,
    task: Dict[str, Any],
    state: Dict[str, Any],
    step: Any,
) -> str:
    target_repo_root = resolve_target_repo_root(task=task, state=state)

    if isinstance(step, dict):
        for key in ("cwd", "working_dir", "workdir"):
            value = str(step.get(key) or "").strip()
            if not value:
                continue
            expanded = os.path.expandvars(os.path.expanduser(value))
            if os.path.isabs(expanded):
                return os.path.normpath(expanded)
            if target_repo_root:
                return os.path.normpath(os.path.join(target_repo_root, expanded))
            return os.path.normpath(expanded)

    if target_repo_root:
        return target_repo_root

    return str(state.get("task_dir") or "")


def target_routed_context(
    *,
    task: Dict[str, Any],
    state: Dict[str, Any],
    step: Any,
    workspace_root: Any,
    operator_session_id_from_payloads: OperatorSessionResolver,
) -> Dict[str, Any]:
    target_repo_root = sync_target_repo_context(task=task, state=state)
    cwd = resolve_step_cwd(task=task, state=state, step=step)
    context = {
        "cwd": cwd,
        "task_dir": state.get("task_dir"),
        "workspace_root": state.get("workspace_root") or workspace_root,
        "target_repo_root": target_repo_root,
        "target_routing_enabled": bool(target_repo_root),
    }
    operator_session_id = operator_session_id_from_payloads(task, state)
    if operator_session_id:
        context["operator_session_id"] = operator_session_id
    return context


__all__ = [
    "normalize_target_repo_root",
    "extract_target_repo_root_from_mapping",
    "resolve_target_repo_root",
    "sync_target_repo_context",
    "resolve_step_cwd",
    "target_routed_context",
]
