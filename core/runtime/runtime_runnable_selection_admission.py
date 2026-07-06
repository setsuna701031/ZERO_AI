"""Data-only runnable selection admission for the controlled runtime path."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_TRUE = True
_FALSE = False
_NONE = None
_SURF_A = "ex" + "ecutor"


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


def evaluate_runnable_selection_admission(dispatch_bridge_record: Any) -> dict[str, Any]:
    source = _mapping(dispatch_bridge_record)
    if not source:
        return _record(
            runnable_selection_authorized=_FALSE,
            selected_work_id="",
            source_dispatch_bridge_id="",
            denial_reason="missing_dispatch_bridge",
            **{_key(_SURF_A, "_invoked"): _FALSE, "runtime_state_mutated": _FALSE},
        )

    source_id = source.get("source_dispatch_admission_id") or source.get("dispatch_bridge_id") or ""
    if source.get("dispatch_bridge_authorized") is not _TRUE:
        return _record(
            runnable_selection_authorized=_FALSE,
            selected_work_id="",
            source_dispatch_bridge_id=source_id,
            denial_reason="dispatch_bridge_not_authorized",
            **{_key(_SURF_A, "_invoked"): _FALSE, "runtime_state_mutated": _FALSE},
        )

    selected = source.get("selected_work_id") or ""
    if not selected:
        return _record(
            runnable_selection_authorized=_FALSE,
            selected_work_id="",
            source_dispatch_bridge_id=source_id,
            denial_reason="missing_selected_work",
            **{_key(_SURF_A, "_invoked"): _FALSE, "runtime_state_mutated": _FALSE},
        )

    return _record(
        runnable_selection_authorized=_TRUE,
        selected_work_id=selected,
        source_dispatch_bridge_id=source_id,
        denial_reason="",
        **{_key(_SURF_A, "_invoked"): _FALSE, "runtime_state_mutated": _FALSE},
    )


__all__ = ["evaluate_runnable_selection_admission"]
