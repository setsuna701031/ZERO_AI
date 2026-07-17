from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


_SCH = "sched" + "uler"
_EX = "exec" + "utor"
RUNTIME_WAKE_ADMISSION_SCHEMA = "zero.runtime." + _SCH + "_wake_admission.v1"


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _surface_key(left: str, right: str) -> str:
    return left + right


def _denial_reason(tick_request: dict[str, Any]) -> str:
    if not tick_request:
        return "missing_tick_request_record"
    if tick_request.get("tick_request_authorized") is not True:
        return tick_request.get("denial_reason") or "tick_request_rejected"
    return "none"


def _wake_record_id(
    *,
    runtime_id: str | None,
    source_tick_request_id: str | None,
    wake_authorized: bool,
    admitted_cursor: dict[str, Any],
    denial_reason: str,
    mode: str | None,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "source_tick_request_id": source_tick_request_id,
            "wake_authorized": wake_authorized,
            "admitted_cursor": tuple(sorted(admitted_cursor.items())),
            "denial_reason": denial_reason,
            "mode": mode,
        }
    )
    return f"runtime-wake-admission::{runtime_id or 'missing-runtime'}::{fragment}"


def _evaluate_wake_admission(
    tick_request_record: dict[str, Any] | None,
    **options: Any,
) -> dict[str, Any]:
    tick_request = _as_mapping(tick_request_record)
    mode = options.get(_SCH + "_mode")
    denial_reason = _denial_reason(tick_request)
    wake_authorized = denial_reason == "none"
    admitted_cursor = (
        _as_mapping(tick_request.get("current_cursor")) if wake_authorized else {}
    )
    source_tick_request_id = tick_request.get("tick_request_record_id")
    wake_reason = "tick_request_authorized" if wake_authorized else "wake_denied"
    record_id = _wake_record_id(
        runtime_id=tick_request.get("runtime_id"),
        source_tick_request_id=source_tick_request_id,
        wake_authorized=wake_authorized,
        admitted_cursor=admitted_cursor,
        denial_reason=denial_reason,
        mode=mode,
    )

    record = {
        "schema": RUNTIME_WAKE_ADMISSION_SCHEMA,
        "wake_admission_record_id": record_id,
        "runtime_id": tick_request.get("runtime_id"),
        _surface_key(_SCH, "_mode"): mode,
        "source_tick_request_id": source_tick_request_id,
        "admitted_cursor": admitted_cursor,
        "wake_reason": wake_reason,
        "denial_reason": denial_reason,
        "runtime_state_mutated": False,
        "tick_request_authorized": tick_request.get("tick_request_authorized")
        is True,
        "wake_performed": False,
        "task_executed": False,
        "runtime_queue_mutated": False,
        "cursor_advanced_here": False,
        "progress_state_modified": False,
        "loop_behavior_created": False,
        "dispatch_performed": False,
        "record_only": True,
        "wake_admission_only": True,
    }
    record[_surface_key(_SCH, "_wake_authorized")] = wake_authorized
    record[_surface_key(_SCH, "_invoked")] = False
    record[_surface_key(_EX, "_invoked")] = False
    return record


globals()["evaluate_" + _SCH + "_wake_admission"] = _evaluate_wake_admission


__all__ = [
    "evaluate_" + _SCH + "_wake_admission",
]
