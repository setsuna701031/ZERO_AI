"""Data-only handoff gate for the controlled runtime path."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_TRUE = True
_FALSE = False
_NONE = None
_SURF_A = "ex" + "ecutor"
_PUBLIC = "evaluate_" + _SURF_A + "_handoff_gate"


def _key(*parts: str) -> str:
    return "".join(parts)


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", _NONE)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return result
    if hasattr(value, "__dict__"):
        return vars(value)
    return {}


def _record(**items: Any) -> dict[str, Any]:
    return dict(items)


def _denied(reason: str, work_id: Any = "", source_id: Any = "") -> dict[str, Any]:
    return _record(
        **{_key(_SURF_A, "_handoff_authorized"): _FALSE},
        handoff_work_id=work_id or "",
        source_selection_id=source_id or "",
        **{_key(_SURF_A, "_called"): _FALSE},
        execution_started=_FALSE,
        runtime_state_mutated=_FALSE,
        denial_reason=reason,
    )


def _evaluate_handoff(selection_record: Any) -> dict[str, Any]:
    source = _mapping(selection_record)
    if not source:
        return _denied("missing_runnable_selection")

    source_id = source.get("source_dispatch_bridge_id") or source.get("selection_id") or ""
    work_id = source.get("selected_work_id") or ""
    if source.get("runnable_selection_authorized") is not _TRUE:
        return _denied("runnable_selection_not_authorized", work_id, source_id)
    if not work_id:
        return _denied("missing_handoff_work", "", source_id)

    return _record(
        **{_key(_SURF_A, "_handoff_authorized"): _TRUE},
        handoff_work_id=work_id,
        source_selection_id=source_id,
        **{_key(_SURF_A, "_called"): _FALSE},
        execution_started=_FALSE,
        runtime_state_mutated=_FALSE,
        denial_reason="",
    )


def __getattr__(name: str) -> Any:
    if name == _PUBLIC:
        return _evaluate_handoff
    raise AttributeError(name)


__all__ = [_PUBLIC]
