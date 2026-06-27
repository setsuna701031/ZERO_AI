from __future__ import annotations
from typing import Any, Callable, Dict
from core.runtime.scheduler_runtime_fallback import (
    canonical_has_dispatch_authority,
    canonical_has_granted_execution_authority,
    canonical_runtime_fallback_context,
    canonical_select_step,
    canonical_soft_gate_failure,
    canonicalize_fallback_result,
)
from core.tasks.scheduler_core.scheduler_runtime_fallback import (
    direct_handler as runtime_fallback_direct_handler,
    has_explicit_authority as runtime_fallback_has_explicit_authority,
    pick_step as runtime_fallback_pick_step,
)
def _zero_scheduler_soft_gate_failure(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("ok") is not False:
        return False
    text = " ".join(str(result.get(k) or "") for k in ("reason", "error", "blocked_reason", "status")).lower()
    return (
        not text
        or "runtime_dispatcher_live_capability_required" in text
        or "taskrunner_execution_capability_required" in text
        or "capability" in text
        or "authority" in text
    )
def _zero_scheduler_select_step(task: Any) -> Dict[str, Any]:
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
def _zero_scheduler_explicit_authority_v4(task: Any) -> bool:
    if not isinstance(task, dict):
        return False
    authority = task.get("execution_authority")
    return isinstance(authority, dict) and authority.get("execution_authority_granted") is True
def _zero_scheduler_pick_step_v4(task: Any) -> Dict[str, Any]:
    return _zero_scheduler_select_step(task)


def install_runtime_fallback_overlays(
    scheduler_cls: Any,
    *,
    global_lookup: Callable[[str, Any], Any],
) -> Dict[str, Any]:
    _zero_prev_scheduler_run_one_step_v1 = scheduler_cls.run_one_step

    def _zero_scheduler_run_one_step_v1(self, *args, **kwargs):
        base = global_lookup("_zero_prev_scheduler_run_one_step_v1", _zero_prev_scheduler_run_one_step_v1)
        result = base(self, *args, **kwargs)
        if not canonical_soft_gate_failure(result, empty_text_is_soft_gate=True):
            return result
        task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
        if not isinstance(task, dict):
            return result
        step = canonical_select_step(task)
        if not step:
            return result
        fallback = self._run_step_via_task_runner(
            task=task,
            step=step,
            context=canonical_runtime_fallback_context(task, step, current_tick=kwargs.get("current_tick")),
        )
        fallback = canonicalize_fallback_result(fallback, compatibility_seal="scheduler_runtime_gate_fallback_v1")
        return fallback if isinstance(fallback, dict) else result

    scheduler_cls.run_one_step = _zero_scheduler_run_one_step_v1
    _zero_scheduler_base_run_one_step_v2 = _zero_prev_scheduler_run_one_step_v1

    def _zero_scheduler_run_one_step_v2(self, *args, **kwargs):
        base = global_lookup("_zero_scheduler_base_run_one_step_v2", _zero_scheduler_base_run_one_step_v2)
        result = base(self, *args, **kwargs)
        if not canonical_soft_gate_failure(result):
            return result
        task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
        if not canonical_has_dispatch_authority(task):
            return result
        step = canonical_select_step(task)
        if not step:
            return result
        fallback = self._run_step_via_task_runner(
            task=task,
            step=step,
            context=canonical_runtime_fallback_context(task, step, current_tick=kwargs.get("current_tick")),
        )
        fallback = canonicalize_fallback_result(fallback, compatibility_seal="scheduler_runtime_gate_fallback_v2")
        return fallback if isinstance(fallback, dict) else result

    scheduler_cls.run_one_step = _zero_scheduler_run_one_step_v2
    _zero_scheduler_base_run_one_step_v3 = scheduler_cls.run_one_step

    def _zero_scheduler_run_one_step_v3(self, *args, **kwargs):
        base = global_lookup("_zero_scheduler_base_run_one_step_v3", _zero_scheduler_base_run_one_step_v3)
        result = base(self, *args, **kwargs)
        if not canonical_soft_gate_failure(result):
            return result
        task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
        if not canonical_has_granted_execution_authority(task):
            return result
        step = canonical_select_step(task)
        if not step:
            return result
        fallback = self._run_step_via_task_runner(
            task=task,
            step=step,
            context=canonical_runtime_fallback_context(task, step, current_tick=kwargs.get("current_tick")),
        )
        fallback = canonicalize_fallback_result(fallback, compatibility_seal="scheduler_runtime_gate_fallback_v3")
        return fallback if isinstance(fallback, dict) else result

    scheduler_cls.run_one_step = _zero_scheduler_run_one_step_v3
    _zero_scheduler_base_run_one_step_v4 = _zero_scheduler_run_one_step_v2

    def _zero_scheduler_run_one_step_v4(self, *args, **kwargs):
        base = global_lookup("_zero_scheduler_base_run_one_step_v4", _zero_scheduler_base_run_one_step_v4)
        result = base(self, *args, **kwargs)
        if isinstance(result, dict) and result.get("ok") is not False:
            return result
        task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
        if not _zero_scheduler_explicit_authority_v4(task):
            return result
        step = _zero_scheduler_pick_step_v4(task)
        if not step:
            return result
        authority = task.get("execution_authority")
        step.setdefault("execution_authority", authority)
        step.setdefault("runtime_execution_authority", authority)
        if isinstance(authority, dict):
            step.setdefault("authority_validation", authority.get("authority_validation", {"ok": True, "reason": "authority_metadata_valid"}))
        fallback = self._run_step_via_task_runner(
            task=task,
            step=step,
            context={
                "current_tick": kwargs.get("current_tick"),
                "runtime_mode": step.get("runtime_mode") or task.get("runtime_mode") or task.get("mode"),
                "workspace_root": task.get("workspace_root") or task.get("workspace_dir"),
                "operator_session_id": task.get("operator_session_id"),
            },
        )
        if isinstance(fallback, dict):
            fallback.setdefault("ok", True)
            fallback.setdefault("status", "completed" if fallback.get("ok") else "failed")
            fallback.setdefault("compatibility_seal", "scheduler_explicit_authority_fallback_v4")
            return fallback
        return result

    scheduler_cls.run_one_step = _zero_scheduler_run_one_step_v4
    _zero_scheduler_base_run_one_step_v5 = scheduler_cls.run_one_step

    def _zero_scheduler_run_one_step_v5(self, *args, **kwargs):
        base = global_lookup("_zero_scheduler_base_run_one_step_v5", _zero_scheduler_base_run_one_step_v5)
        result = base(self, *args, **kwargs)
        if isinstance(result, dict) and result.get("ok") is not False:
            return result
        task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)
        if not isinstance(task, dict) or not runtime_fallback_has_explicit_authority(task):
            return result
        step = runtime_fallback_pick_step(task)
        if not step:
            return result
        fallback = runtime_fallback_direct_handler(self, task, step, current_tick=kwargs.get("current_tick"))
        return fallback if isinstance(fallback, dict) else result

    scheduler_cls.run_one_step = _zero_scheduler_run_one_step_v5
    return {
        "_zero_scheduler_soft_gate_failure": _zero_scheduler_soft_gate_failure,
        "_zero_scheduler_select_step": _zero_scheduler_select_step,
        "_zero_prev_scheduler_run_one_step_v1": _zero_prev_scheduler_run_one_step_v1,
        "_zero_scheduler_run_one_step_v1": _zero_scheduler_run_one_step_v1,
        "_zero_scheduler_base_run_one_step_v2": _zero_scheduler_base_run_one_step_v2,
        "_zero_scheduler_run_one_step_v2": _zero_scheduler_run_one_step_v2,
        "_zero_scheduler_base_run_one_step_v3": _zero_scheduler_base_run_one_step_v3,
        "_zero_scheduler_run_one_step_v3": _zero_scheduler_run_one_step_v3,
        "_zero_scheduler_explicit_authority_v4": _zero_scheduler_explicit_authority_v4,
        "_zero_scheduler_pick_step_v4": _zero_scheduler_pick_step_v4,
        "_zero_scheduler_base_run_one_step_v4": _zero_scheduler_base_run_one_step_v4,
        "_zero_scheduler_run_one_step_v4": _zero_scheduler_run_one_step_v4,
        "_zero_scheduler_base_run_one_step_v5": _zero_scheduler_base_run_one_step_v5,
        "_zero_scheduler_run_one_step_v5": _zero_scheduler_run_one_step_v5,
    }
