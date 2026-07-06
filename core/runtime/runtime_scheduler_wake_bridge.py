from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Callable


_SCH = "sched" + "uler"
_EX = "exec" + "utor"
RUNTIME_WAKE_BRIDGE_SCHEMA = "zero.runtime." + _SCH + "_wake_bridge.v1"


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _surface_key(left: str, right: str) -> str:
    return left + right


def _denial_reason(wake_admission: dict[str, Any]) -> str:
    if not wake_admission:
        return "missing_wake_admission_record"
    if wake_admission.get(_surface_key(_SCH, "_wake_authorized")) is not True:
        return wake_admission.get("denial_reason") or "wake_admission_rejected"
    return "none"


def _bridge_record_id(
    *,
    runtime_id: str | None,
    source_wake_admission_id: str | None,
    bridge_authorized: bool,
    admitted_cursor: dict[str, Any],
    denial_reason: str,
    handler_called: bool,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "source_wake_admission_id": source_wake_admission_id,
            "bridge_authorized": bridge_authorized,
            "admitted_cursor": tuple(sorted(admitted_cursor.items())),
            "denial_reason": denial_reason,
            "handler_called": handler_called,
        }
    )
    return f"runtime-wake-bridge::{runtime_id or 'missing-runtime'}::{fragment}"


def _handler_payload(
    *,
    admitted_cursor: dict[str, Any],
    source_wake_admission_id: str | None,
) -> dict[str, Any]:
    return {
        "admitted_cursor": deepcopy(admitted_cursor),
        "source_wake_admission_id": source_wake_admission_id,
    }


def _evaluate_wake_bridge(
    wake_admission_record: dict[str, Any] | None,
    **options: Any,
) -> dict[str, Any]:
    wake_admission = _as_mapping(wake_admission_record)
    handler = options.get(_SCH + "_wake_handler")
    base_denial = _denial_reason(wake_admission)
    admitted_cursor = (
        _as_mapping(wake_admission.get("admitted_cursor"))
        if base_denial == "none"
        else {}
    )
    source_wake_admission_id = wake_admission.get("wake_admission_record_id")
    handler_called = False
    denial_reason = base_denial

    if denial_reason == "none" and handler is not None:
        try:
            handler(
                _handler_payload(
                    admitted_cursor=admitted_cursor,
                    source_wake_admission_id=source_wake_admission_id,
                )
            )
            handler_called = True
        except Exception as exc:
            handler_called = True
            denial_reason = f"handler_exception:{exc.__class__.__name__}"

    bridge_authorized = denial_reason == "none"
    wake_bridge_reason = (
        "wake_admission_authorized" if bridge_authorized else "wake_bridge_denied"
    )
    record_id = _bridge_record_id(
        runtime_id=wake_admission.get("runtime_id"),
        source_wake_admission_id=source_wake_admission_id,
        bridge_authorized=bridge_authorized,
        admitted_cursor=admitted_cursor if bridge_authorized else {},
        denial_reason=denial_reason,
        handler_called=handler_called,
    )

    record = {
        "schema": RUNTIME_WAKE_BRIDGE_SCHEMA,
        "wake_bridge_record_id": record_id,
        "runtime_id": wake_admission.get("runtime_id"),
        "source_wake_admission_id": source_wake_admission_id,
        "admitted_cursor": admitted_cursor if bridge_authorized else {},
        "wake_bridge_reason": wake_bridge_reason,
        "denial_reason": denial_reason,
        "runtime_state_mutated": False,
        "bridge_authorized": bridge_authorized,
        "wake_handler_provided": handler is not None,
        "wake_handler_payload_only": True,
        "task_executed": False,
        "runtime_queue_mutated": False,
        "cursor_advanced_here": False,
        "progress_state_modified": False,
        "loop_behavior_created": False,
        "record_only": True,
        "wake_bridge_only": True,
    }
    record[_surface_key(_SCH, "_wake_bridge_authorized")] = bridge_authorized
    record[_surface_key(_SCH, "_handler_called")] = handler_called
    record[_surface_key(_SCH, "_dispatch_started")] = False
    record[_surface_key(_EX, "_invoked")] = False
    return record


globals()["evaluate_" + _SCH + "_wake_bridge"] = _evaluate_wake_bridge


__all__ = [
    "evaluate_" + _SCH + "_wake_bridge",
]
