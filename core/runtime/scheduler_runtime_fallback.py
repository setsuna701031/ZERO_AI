from __future__ import annotations

from typing import Any


def canonical_soft_gate_failure(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("ok") is not False:
        return False

    text = " ".join(
        str(result.get(key) or "")
        for key in ("reason", "error", "blocked_reason", "status")
    ).lower()

    return (
        not text
        or "runtime_dispatcher_live_capability_required" in text
        or "taskrunner_execution_capability_required" in text
        or "runtime_execution_capability_not_validated" in text
        or "capability" in text
        or "authority" in text
    )


def canonical_select_step(task: Any) -> dict[str, Any]:
    if not isinstance(task, dict):
        return {}

    steps = task.get("steps")
    if not isinstance(steps, list) or not steps:
        return {}

    try:
        index = int(task.get("current_step_index", task.get("step_index", 0)))
    except Exception:
        index = 0

    if index < 0 or index >= len(steps):
        index = 0

    step = steps[index]
    return step if isinstance(step, dict) else {}


def canonical_has_dispatch_authority(task: Any) -> bool:
    if not isinstance(task, dict):
        return False

    authority = task.get("execution_authority")
    if isinstance(authority, dict) and authority.get("execution_authority_granted") is True:
        return True

    for key in (
        "runtime_execution_capability",
        "dispatch_execution_capability",
        "runtime_dispatch_capability",
        "execution_capability",
    ):
        if task.get(key):
            return True

    return False


def canonical_has_explicit_authority(task: Any) -> bool:
    authority = task.get("execution_authority") if isinstance(task, dict) else None
    return isinstance(authority, dict)


def canonical_has_granted_execution_authority(task: Any) -> bool:
    authority = task.get("execution_authority") if isinstance(task, dict) else None
    return (
        isinstance(authority, dict)
        and authority.get("execution_authority_granted") is True
    )


def canonical_attach_authority_to_step(
    task: Any,
    step: Any,
) -> dict[str, Any]:
    if not isinstance(step, dict):
        return {}

    if not isinstance(task, dict):
        return step

    authority = task.get("execution_authority")
    step.setdefault("execution_authority", authority)
    step.setdefault("runtime_execution_authority", authority)

    if isinstance(authority, dict):
        step.setdefault(
            "authority_validation",
            authority.get(
                "authority_validation",
                {"ok": True, "reason": "authority_metadata_valid"},
            ),
        )

    return step


def canonical_runtime_fallback_context(
    task: Any,
    step: Any,
    *,
    current_tick: Any = None,
) -> dict[str, Any]:
    task_dict = task if isinstance(task, dict) else {}
    step_dict = step if isinstance(step, dict) else {}

    return {
        "current_tick": current_tick,
        "runtime_mode": (
            step_dict.get("runtime_mode")
            or task_dict.get("runtime_mode")
            or task_dict.get("mode")
        ),
        "workspace_root": task_dict.get("workspace_root") or task_dict.get("workspace_dir"),
        "operator_session_id": task_dict.get("operator_session_id"),
    }


def canonicalize_fallback_result(
    fallback: Any,
    *,
    compatibility_seal: str,
) -> Any:
    if not isinstance(fallback, dict):
        return fallback

    fallback.setdefault("ok", True)
    fallback.setdefault("status", "completed" if fallback.get("ok") else "failed")
    fallback.setdefault("compatibility_seal", compatibility_seal)
    return fallback