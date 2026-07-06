from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_CURSOR_ADVANCE_AUTHORITY_SCHEMA = (
    "zero.runtime.cursor_advance_authority.v1"
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _cursor_advance_record_id(
    *,
    runtime_id: str | None,
    source_progress_id: str | None,
    previous_cursor: dict[str, Any],
    next_cursor: dict[str, Any],
    cursor_advance_authorized: bool,
    denial_reason: str,
) -> str:
    fragment = _stable_fragment(
        {
            "runtime_id": runtime_id,
            "source_progress_id": source_progress_id,
            "previous_cursor": tuple(sorted(previous_cursor.items())),
            "next_cursor": tuple(sorted(next_cursor.items())),
            "cursor_advance_authorized": cursor_advance_authorized,
            "denial_reason": denial_reason,
        }
    )
    return f"runtime-cursor-advance::{runtime_id or 'missing-runtime'}::{fragment}"


def _denial_reason(
    progress_apply: dict[str, Any],
    next_cursor: dict[str, Any],
) -> str:
    reasons: list[str] = []
    if not progress_apply:
        reasons.append("missing_progress_apply_record")
    elif progress_apply.get("progress_apply_allowed") is not True:
        reasons.append(progress_apply.get("denial_reason") or "progress_apply_rejected")
    if not next_cursor:
        reasons.append("missing_next_candidate")
    return ";".join(reasons) if reasons else "none"


def evaluate_cursor_advance(
    progress_apply_record: dict[str, Any] | None,
    current_cursor: dict[str, Any] | None,
    next_candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    progress_apply = _as_mapping(progress_apply_record)
    previous_cursor = _as_mapping(current_cursor)
    next_cursor = _as_mapping(next_candidate)
    denial_reason = _denial_reason(progress_apply, next_cursor)
    cursor_advance_authorized = denial_reason == "none"
    source_progress_id = progress_apply.get("progress_apply_record_id")
    record_id = _cursor_advance_record_id(
        runtime_id=progress_apply.get("runtime_id"),
        source_progress_id=source_progress_id,
        previous_cursor=previous_cursor,
        next_cursor=next_cursor if cursor_advance_authorized else {},
        cursor_advance_authorized=cursor_advance_authorized,
        denial_reason=denial_reason,
    )

    return {
        "schema": RUNTIME_CURSOR_ADVANCE_AUTHORITY_SCHEMA,
        "cursor_advance_record_id": record_id,
        "runtime_id": progress_apply.get("runtime_id"),
        "cursor_advance_authorized": cursor_advance_authorized,
        "previous_cursor": previous_cursor,
        "next_cursor": next_cursor if cursor_advance_authorized else {},
        "source_progress_id": source_progress_id,
        "denial_reason": denial_reason,
        "runtime_state_mutated": False,
        "progress_apply_allowed": progress_apply.get("progress_apply_allowed") is True,
        "progress_record_created": progress_apply.get("progress_record_created")
        is True,
        "execution_admission_called": False,
        "worker_called": False,
        "task_executed": False,
        "runtime_queue_mutated": False,
        "loop_continued": False,
        "next_tick_requested": False,
        "retry_scheduled": False,
        "daemon_started": False,
        "thread_created": False,
        "record_only": True,
        "cursor_authority_only": True,
    }


__all__ = [
    "RUNTIME_CURSOR_ADVANCE_AUTHORITY_SCHEMA",
    "evaluate_cursor_advance",
]
