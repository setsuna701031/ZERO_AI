from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Mapping


RUNTIME_AUTONOMOUS_CHECKPOINT_SCHEMA = "zero.runtime.autonomous_checkpoint.v1"

VALID_RUNTIME_STATES = ("active", "paused", "stopped")


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _non_negative_int(value: Any, default: int = -1) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 0 else default


@dataclass(frozen=True)
class RuntimeLoopCheckpointRecord:
    schema: str
    checkpoint_id: str
    runtime_session_id: str
    active_cursor: str
    current_tick_index: int
    last_completed_work_id: str
    lease_id: str
    lease_expiry_tick: int
    lease_expiry: int
    runtime_state: str
    paused: bool
    stopped: bool
    valid_checkpoint: bool
    denial_reason: str
    runtime_state_mutated: bool
    cursor_advanced: bool
    work_started: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_runtime_loop_checkpoint_record(
    *,
    checkpoint_id: str,
    runtime_session_id: str,
    active_cursor: str,
    current_tick_index: int,
    last_completed_work_id: str,
    lease_id: str,
    lease_expiry_tick: int,
    runtime_state: str = "active",
) -> dict[str, Any]:
    state = _text(runtime_state) or "active"
    tick = _non_negative_int(current_tick_index)
    expiry = _non_negative_int(lease_expiry_tick)

    denial = ""
    valid = True
    if not _text(checkpoint_id):
        denial = "missing_checkpoint_id"
        valid = False
    elif not _text(runtime_session_id):
        denial = "missing_runtime_session_id"
        valid = False
    elif not _text(active_cursor):
        denial = "missing_active_cursor"
        valid = False
    elif tick < 0:
        denial = "invalid_current_tick_index"
        valid = False
    elif not _text(lease_id):
        denial = "missing_lease_id"
        valid = False
    elif expiry < 0:
        denial = "invalid_lease_expiry_tick"
        valid = False
    elif state not in VALID_RUNTIME_STATES:
        denial = "invalid_runtime_state"
        valid = False

    return RuntimeLoopCheckpointRecord(
        schema=RUNTIME_AUTONOMOUS_CHECKPOINT_SCHEMA,
        checkpoint_id=_text(checkpoint_id),
        runtime_session_id=_text(runtime_session_id),
        active_cursor=_text(active_cursor),
        current_tick_index=max(0, tick),
        last_completed_work_id=_text(last_completed_work_id),
        lease_id=_text(lease_id),
        lease_expiry_tick=max(0, expiry),
        lease_expiry=max(0, expiry),
        runtime_state=state,
        paused=state == "paused",
        stopped=state == "stopped",
        valid_checkpoint=valid,
        denial_reason=denial,
        runtime_state_mutated=False,
        cursor_advanced=False,
        work_started=False,
    ).to_dict()


def validate_runtime_loop_checkpoint_record(checkpoint_record: Any) -> dict[str, Any]:
    record = _mapping(checkpoint_record)
    problems: list[str] = []

    if not record:
        problems.append("checkpoint_missing")
    elif record.get("schema") != RUNTIME_AUTONOMOUS_CHECKPOINT_SCHEMA:
        problems.append("checkpoint_schema_invalid")

    if record:
        for field in (
            "checkpoint_id",
            "runtime_session_id",
            "active_cursor",
            "lease_id",
        ):
            if not _text(record.get(field)):
                problems.append(f"{field}_missing")

        if _non_negative_int(record.get("current_tick_index")) < 0:
            problems.append("current_tick_index_invalid")
        if _non_negative_int(record.get("lease_expiry_tick")) < 0:
            problems.append("lease_expiry_tick_invalid")
        if _text(record.get("runtime_state")) not in VALID_RUNTIME_STATES:
            problems.append("runtime_state_invalid")
        if record.get("valid_checkpoint") is not True:
            problems.append("checkpoint_marked_invalid")

    return {
        "schema": RUNTIME_AUTONOMOUS_CHECKPOINT_SCHEMA,
        "checkpoint_valid": not problems,
        "checkpoint_id": record.get("checkpoint_id"),
        "runtime_session_id": record.get("runtime_session_id"),
        "active_cursor": record.get("active_cursor"),
        "current_tick_index": _non_negative_int(record.get("current_tick_index"), 0),
        "last_completed_work_id": _text(record.get("last_completed_work_id")),
        "lease_id": record.get("lease_id"),
        "lease_expiry_tick": _non_negative_int(record.get("lease_expiry_tick"), 0),
        "lease_expiry": _non_negative_int(record.get("lease_expiry_tick"), 0),
        "runtime_state": _text(record.get("runtime_state")),
        "paused": record.get("paused") is True,
        "stopped": record.get("stopped") is True,
        "problems": problems,
        "denial_reason": problems[0] if problems else "",
        "runtime_state_mutated": False,
        "cursor_advanced": False,
        "work_started": False,
    }


__all__ = [
    "RUNTIME_AUTONOMOUS_CHECKPOINT_SCHEMA",
    "VALID_RUNTIME_STATES",
    "RuntimeLoopCheckpointRecord",
    "build_runtime_loop_checkpoint_record",
    "validate_runtime_loop_checkpoint_record",
]
