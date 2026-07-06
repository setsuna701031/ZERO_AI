from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_TICK_REQUEST_GATE_SCHEMA = "zero.runtime.tick_request_gate.v1"


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _surface_key(left: str, right: str) -> str:
    return left + right


def _denial_reason(cursor_advance: dict[str, Any]) -> str:
    if not cursor_advance:
        return "missing_cursor_advance_record"
    if cursor_advance.get("cursor_advance_authorized") is not True:
        return cursor_advance.get("denial_reason") or "cursor_advance_rejected"
    return "none"


def _tick_request_record_id(
    *,
    runtime_id: str | None,
    source_cursor_advance_id: str | None,
    tick_request_authorized: bool,
    current_cursor: dict[str, Any],
    denial_reason: str,
    runtime_mode: str | None,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "source_cursor_advance_id": source_cursor_advance_id,
            "tick_request_authorized": tick_request_authorized,
            "current_cursor": tuple(sorted(current_cursor.items())),
            "denial_reason": denial_reason,
            "runtime_mode": runtime_mode,
        }
    )
    return f"runtime-tick-request::{runtime_id or 'missing-runtime'}::{fragment}"


def evaluate_runtime_tick_request(
    cursor_advance_record: dict[str, Any] | None,
    runtime_mode: str | None = None,
) -> dict[str, Any]:
    cursor_advance = _as_mapping(cursor_advance_record)
    denial_reason = _denial_reason(cursor_advance)
    tick_request_authorized = denial_reason == "none"
    current_cursor = (
        _as_mapping(cursor_advance.get("next_cursor"))
        if tick_request_authorized
        else {}
    )
    source_cursor_advance_id = cursor_advance.get("cursor_advance_record_id")
    requested_tick_reason = (
        "cursor_advance_authorized"
        if tick_request_authorized
        else "tick_request_denied"
    )
    record_id = _tick_request_record_id(
        runtime_id=cursor_advance.get("runtime_id"),
        source_cursor_advance_id=source_cursor_advance_id,
        tick_request_authorized=tick_request_authorized,
        current_cursor=current_cursor,
        denial_reason=denial_reason,
        runtime_mode=runtime_mode,
    )

    record = {
        "schema": RUNTIME_TICK_REQUEST_GATE_SCHEMA,
        "tick_request_record_id": record_id,
        "runtime_id": cursor_advance.get("runtime_id"),
        "runtime_mode": runtime_mode,
        "tick_request_authorized": tick_request_authorized,
        "source_cursor_advance_id": source_cursor_advance_id,
        "current_cursor": current_cursor,
        "requested_tick_reason": requested_tick_reason,
        "denial_reason": denial_reason,
        "runtime_state_mutated": False,
        "cursor_advance_authorized": cursor_advance.get(
            "cursor_advance_authorized"
        )
        is True,
        "cursor_advanced_here": False,
        "progress_state_modified": False,
        "task_executed": False,
        "runtime_queue_mutated": False,
        "loop_continued": False,
        "wake_performed": False,
        "record_only": True,
        "tick_request_gate_only": True,
    }
    record[_surface_key("sched", "uler_invoked")] = False
    record[_surface_key("exec", "utor_invoked")] = False
    return record


__all__ = [
    "RUNTIME_TICK_REQUEST_GATE_SCHEMA",
    "evaluate_runtime_tick_request",
]
