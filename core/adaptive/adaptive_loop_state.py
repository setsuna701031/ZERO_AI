from __future__ import annotations

"""State vocabulary for Adaptive Loop v2 observation deltas."""

from enum import Enum
from typing import Any, Mapping


class AdaptiveLoopState(str, Enum):
    INITIAL = "initial"
    PROGRESSING = "progressing"
    REGRESSED = "regressed"
    STALLED = "stalled"
    TERMINAL = "terminal"


def clean_adaptive_loop_state(value: AdaptiveLoopState | str | Any) -> str:
    raw = value.value if isinstance(value, AdaptiveLoopState) else str(value or "").strip().lower()
    try:
        return AdaptiveLoopState(raw).value
    except ValueError as exc:
        raise ValueError("adaptive_loop_requires_valid_state") from exc


def classify_adaptive_loop_state(*, delta: Mapping[str, Any], replan_state: Mapping[str, Any] | None = None) -> str:
    state = replan_state if isinstance(replan_state, Mapping) else {}
    if bool(state.get("terminal")) or state.get("loop_action") in {"complete", "blocked", "refuse", "stop", "wait_for_user"}:
        return AdaptiveLoopState.TERMINAL.value
    if delta.get("previous_cycle_index") is None:
        return AdaptiveLoopState.INITIAL.value
    if bool(delta.get("regressed")):
        return AdaptiveLoopState.REGRESSED.value
    if bool(delta.get("has_progress")):
        return AdaptiveLoopState.PROGRESSING.value
    if bool(delta.get("stalled")):
        return AdaptiveLoopState.STALLED.value
    return AdaptiveLoopState.PROGRESSING.value


__all__ = ["AdaptiveLoopState", "classify_adaptive_loop_state", "clean_adaptive_loop_state"]
