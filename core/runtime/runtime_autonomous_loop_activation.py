"""Controlled autonomous loop activation records.

This module keeps the first autonomous cycle bounded.  It only creates
activation, tick-cycle, stop, and pause/resume records.  Any real runtime
work must be supplied through an injected handler and remains outside this
module.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _bool(value: Any) -> bool:
    return bool(value) is True


def _get(value: Mapping[str, Any], key: str, default: Any = None) -> Any:
    return value.get(key, default)


def _record_id(prefix: str, source: Any) -> str:
    text = str(source or "missing").strip() or "missing"
    return f"{prefix}:{text}"


def evaluate_runtime_loop_activation(
    loop_closure_record: Any,
    *,
    autonomous_mode: Any = None,
    max_iterations: int = 1,
    paused: bool = False,
) -> dict[str, Any]:
    """Authorize a bounded autonomous cycle from a loop closure record."""

    source = _as_mapping(loop_closure_record)
    safe_max = max(0, int(max_iterations or 0))

    base = {
        "loop_activation_authorized": False,
        "loop_activation_id": "loop-activation:denied",
        "source_loop_closure_id": None,
        "activation_reason": "",
        "denial_reason": "",
        "autonomous_mode": str(autonomous_mode or "bounded"),
        "max_iterations": safe_max,
        "pause_requested": bool(paused),
        "tick_cycle_requested": False,
        "runtime_state_mutated": False,
    }

    if source is None:
        base["denial_reason"] = "missing_loop_closure_record"
        return base

    source_id = _get(source, "loop_closure_id") or _get(source, "source_result_validation_id")
    base["source_loop_closure_id"] = source_id
    base["loop_activation_id"] = _record_id("loop-activation", source_id)

    closure_ok = _bool(_get(source, "loop_closure_authorized", _get(source, "progress_apply_adapter_authorized")))
    if not closure_ok:
        base["denial_reason"] = "loop_closure_not_authorized"
        return base

    if paused:
        base["denial_reason"] = "runtime_paused"
        return base

    if safe_max < 1:
        base["denial_reason"] = "max_iterations_exhausted"
        return base

    base.update(
        {
            "loop_activation_authorized": True,
            "activation_reason": "bounded_loop_activation_authorized",
            "tick_cycle_requested": True,
        }
    )
    return base


def run_runtime_tick_cycle(
    loop_activation_record: Any,
    *,
    tick_handler: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Carry an authorized tick-cycle request to an injected handler."""

    source = _as_mapping(loop_activation_record)
    base = {
        "tick_cycle_authorized": False,
        "tick_cycle_id": "tick-cycle:denied",
        "source_loop_activation_id": None,
        "tick_handler_called": False,
        "tick_handler_result_received": False,
        "tick_handler_result": None,
        "cycle_reason": "",
        "denial_reason": "",
        "iteration_index": 0,
        "runtime_state_mutated": False,
    }

    if source is None:
        base["denial_reason"] = "missing_loop_activation_record"
        return base

    source_id = _get(source, "loop_activation_id")
    base["source_loop_activation_id"] = source_id
    base["tick_cycle_id"] = _record_id("tick-cycle", source_id)
    base["iteration_index"] = 1

    if not _bool(_get(source, "loop_activation_authorized")):
        base["denial_reason"] = "loop_activation_not_authorized"
        return base

    if not _bool(_get(source, "tick_cycle_requested")):
        base["denial_reason"] = "tick_cycle_not_requested"
        return base

    base["tick_cycle_authorized"] = True
    base["cycle_reason"] = "bounded_tick_cycle_authorized"

    if tick_handler is None:
        return base

    payload = {
        "source_loop_activation_id": source_id,
        "iteration_index": 1,
    }
    try:
        result = tick_handler(payload)
    except Exception as exc:  # pragma: no cover - exact exception is data only
        base.update(
            {
                "tick_cycle_authorized": False,
                "tick_handler_called": True,
                "tick_handler_result_received": False,
                "denial_reason": f"tick_handler_failed:{type(exc).__name__}",
            }
        )
        return base

    base.update(
        {
            "tick_handler_called": True,
            "tick_handler_result_received": True,
            "tick_handler_result": result,
        }
    )
    return base


def evaluate_runtime_loop_stop_condition(
    tick_cycle_record: Any,
    *,
    iteration_count: int = 1,
    max_iterations: int = 1,
    paused: bool = False,
) -> dict[str, Any]:
    """Evaluate whether the bounded autonomous loop must stop."""

    source = _as_mapping(tick_cycle_record)
    count = max(0, int(iteration_count or 0))
    limit = max(0, int(max_iterations or 0))
    base = {
        "loop_stop_required": True,
        "loop_continue_authorized": False,
        "source_tick_cycle_id": None,
        "stop_reason": "",
        "denial_reason": "",
        "iteration_count": count,
        "max_iterations": limit,
        "pause_requested": bool(paused),
        "runtime_state_mutated": False,
    }

    if source is None:
        base["stop_reason"] = "missing_tick_cycle_record"
        return base

    base["source_tick_cycle_id"] = _get(source, "tick_cycle_id")

    if not _bool(_get(source, "tick_cycle_authorized")):
        base["stop_reason"] = "tick_cycle_not_authorized"
        return base

    if paused:
        base["stop_reason"] = "runtime_paused"
        return base

    if limit < 1 or count >= limit:
        base["stop_reason"] = "max_iterations_reached"
        return base

    base.update(
        {
            "loop_stop_required": False,
            "loop_continue_authorized": True,
            "stop_reason": "continue_within_bounds",
        }
    )
    return base


def evaluate_runtime_pause_resume(command: Any, current_state: Any = None) -> dict[str, Any]:
    """Create a deterministic pause/resume state record."""

    state = _as_mapping(current_state) or {}
    text = str(command or "").strip().lower()
    currently_paused = bool(state.get("runtime_paused", False))

    if text == "pause":
        paused = True
        reason = "pause_requested"
    elif text == "resume":
        paused = False
        reason = "resume_requested"
    else:
        paused = currently_paused
        reason = "no_state_change"

    return {
        "pause_resume_record_id": _record_id("pause-resume", text or "noop"),
        "runtime_paused": paused,
        "state_change_reason": reason,
        "runtime_state_mutated": False,
    }


__all__ = [
    "evaluate_runtime_loop_activation",
    "run_runtime_tick_cycle",
    "evaluate_runtime_loop_stop_condition",
    "evaluate_runtime_pause_resume",
]
