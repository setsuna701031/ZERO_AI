from __future__ import annotations

import copy
from typing import Any, Dict


def normalize_runtime_mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"execute", "replay", "audit", "repair_replay"}:
        return text
    return "execute"


def extract_runtime_mode_from_mapping(value: Any) -> str:
    if not isinstance(value, dict):
        return ""

    for key in ("runtime_mode", "mode", "execution_mode"):
        raw = value.get(key)
        if raw is not None and str(raw).strip():
            return normalize_runtime_mode(raw)

    runtime_context = value.get("runtime_context")
    if isinstance(runtime_context, dict):
        for key in ("runtime_mode", "mode", "execution_mode"):
            raw = runtime_context.get(key)
            if raw is not None and str(raw).strip():
                return normalize_runtime_mode(raw)

    repair_context = value.get("repair_context")
    if isinstance(repair_context, dict):
        raw = repair_context.get("runtime_mode")
        if raw is not None and str(raw).strip():
            return normalize_runtime_mode(raw)

    return ""


def resolve_runtime_mode(
    *,
    task: Dict[str, Any],
    state: Dict[str, Any],
    step: Any = None,
) -> str:
    for payload in (step, state, task):
        mode = extract_runtime_mode_from_mapping(payload)
        if mode:
            return mode
    return "execute"


def apply_runtime_mode_to_step(
    *,
    task: Dict[str, Any],
    state: Dict[str, Any],
    step: Any,
) -> tuple[Dict[str, Any], str]:
    runtime_mode = resolve_runtime_mode(task=task, state=state, step=step)
    normalized_step = copy.deepcopy(step) if isinstance(step, dict) else {}
    normalized_step["runtime_mode"] = runtime_mode
    return normalized_step, runtime_mode


__all__ = [
    "normalize_runtime_mode",
    "extract_runtime_mode_from_mapping",
    "resolve_runtime_mode",
    "apply_runtime_mode_to_step",
]
