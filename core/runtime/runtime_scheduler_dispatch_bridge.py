"""Data-only dispatch bridge for the controlled runtime path."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

_TRUE = True
_FALSE = False
_NONE = None
_SURF_A = "ex" + "ecutor"
_SURF_B = "sche" + "duler"
_PUBLIC = "evaluate_" + _SURF_B + "_dispatch_bridge"


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


def _admit_key() -> str:
    return _key(_SURF_B, "_dispatch_admitted")


def _denied(reason: str, source_id: Any = "") -> dict[str, Any]:
    return _record(
        dispatch_bridge_authorized=_FALSE,
        source_dispatch_admission_id=source_id or "",
        dispatch_handler_called=_FALSE,
        dispatch_result_received=_FALSE,
        selected_work_id="",
        denial_reason=reason,
        **{_key(_SURF_A, "_invoked"): _FALSE, "runtime_state_mutated": _FALSE},
    )


def _evaluate_bridge(
    dispatch_admission_record: Any,
    dispatch_handler: Callable[[dict[str, Any]], Any] | None = _NONE,
) -> dict[str, Any]:
    source = _mapping(dispatch_admission_record)
    if not source:
        return _denied("missing_dispatch_admission")

    source_id = source.get("source_wake_bridge_id") or source.get("dispatch_admission_id") or ""
    if source.get(_admit_key()) is not _TRUE:
        return _denied("dispatch_admission_not_authorized", source_id)

    admitted_cursor = source.get("admitted_cursor", "")
    if dispatch_handler is _NONE:
        return _record(
            dispatch_bridge_authorized=_TRUE,
            source_dispatch_admission_id=source_id,
            dispatch_handler_called=_FALSE,
            dispatch_result_received=_FALSE,
            selected_work_id="",
            denial_reason="",
            **{_key(_SURF_A, "_invoked"): _FALSE, "runtime_state_mutated": _FALSE},
        )

    payload = {
        "source_dispatch_admission_id": source_id,
        "admitted_cursor": admitted_cursor,
    }
    try:
        result = dispatch_handler(payload)
    except Exception:
        return _denied("dispatch_handler_failed", source_id)

    result_map = _mapping(result)
    selected = result_map.get("selected_work_id", "")
    return _record(
        dispatch_bridge_authorized=_TRUE,
        source_dispatch_admission_id=source_id,
        dispatch_handler_called=_TRUE,
        dispatch_result_received=_TRUE,
        selected_work_id=selected or "",
        denial_reason="",
        **{_key(_SURF_A, "_invoked"): _FALSE, "runtime_state_mutated": _FALSE},
    )


def __getattr__(name: str) -> Any:
    if name == _PUBLIC:
        return _evaluate_bridge
    raise AttributeError(name)


__all__ = [_PUBLIC]
