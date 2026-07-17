"""Runtime Scheduler Dispatch Admission.

Data-only authority layer that decides whether scheduler dispatch may be
admitted after a scheduler wake bridge record.

This module intentionally has no direct dependency on runtime execution surfaces.
It emits deterministic admission data only and leaves all downstream effects
outside this authority layer.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeSchedulerDispatchAdmissionRecord:
    """Deterministic data record for dispatch admission."""

    scheduler_dispatch_admitted: bool
    source_wake_bridge_id: str
    admitted_cursor: str
    dispatch_reason: str
    denial_reason: str
    scheduler_dispatch_started: bool
    executor_invoked: bool
    runtime_state_mutated: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_bool(record: Mapping[str, Any], key: str) -> bool:
    return bool(record.get(key) is True)


def _read_text(record: Mapping[str, Any], key: str) -> str:
    value = record.get(key)
    if value is None:
        return ""
    return str(value)


def _deny(reason: str, wake_bridge_record: Mapping[str, Any] | None = None) -> RuntimeSchedulerDispatchAdmissionRecord:
    source_wake_bridge_id = ""
    admitted_cursor = ""

    if isinstance(wake_bridge_record, Mapping):
        source_wake_bridge_id = _read_text(wake_bridge_record, "source_wake_admission_id")
        if not source_wake_bridge_id:
            source_wake_bridge_id = _read_text(wake_bridge_record, "source_wake_bridge_id")
        admitted_cursor = _read_text(wake_bridge_record, "admitted_cursor")

    return RuntimeSchedulerDispatchAdmissionRecord(
        scheduler_dispatch_admitted=False,
        source_wake_bridge_id=source_wake_bridge_id,
        admitted_cursor=admitted_cursor,
        dispatch_reason="",
        denial_reason=reason,
        scheduler_dispatch_started=False,
        executor_invoked=False,
        runtime_state_mutated=False,
    )


def evaluate_scheduler_dispatch_admission(
    wake_bridge_record: Mapping[str, Any] | None,
    dispatch_mode: str | None = None,
) -> RuntimeSchedulerDispatchAdmissionRecord:
    """Evaluate whether scheduler dispatch may be admitted.

    The returned record is data only. A successful admission allows a downstream
    dispatch owner to consider choosing runnable work later, but this function
    never starts dispatch itself.
    """

    if not isinstance(wake_bridge_record, Mapping):
        return _deny("missing_wake_bridge_record")

    if not _read_bool(wake_bridge_record, "scheduler_wake_bridge_authorized"):
        return _deny("wake_bridge_not_authorized", wake_bridge_record)

    source_wake_bridge_id = _read_text(wake_bridge_record, "source_wake_admission_id")
    if not source_wake_bridge_id:
        source_wake_bridge_id = _read_text(wake_bridge_record, "source_wake_bridge_id")

    admitted_cursor = _read_text(wake_bridge_record, "admitted_cursor")

    if not source_wake_bridge_id:
        return _deny("missing_source_wake_bridge_id", wake_bridge_record)

    if not admitted_cursor:
        return _deny("missing_admitted_cursor", wake_bridge_record)

    reason = "wake_bridge_authorized"
    if dispatch_mode:
        reason = f"{reason}:{dispatch_mode}"

    return RuntimeSchedulerDispatchAdmissionRecord(
        scheduler_dispatch_admitted=True,
        source_wake_bridge_id=source_wake_bridge_id,
        admitted_cursor=admitted_cursor,
        dispatch_reason=reason,
        denial_reason="",
        scheduler_dispatch_started=False,
        executor_invoked=False,
        runtime_state_mutated=False,
    )


__all__ = [
    "RuntimeSchedulerDispatchAdmissionRecord",
    "evaluate_scheduler_dispatch_admission",
]
