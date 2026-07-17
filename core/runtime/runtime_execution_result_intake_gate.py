"""Runtime execution result intake gate.

Data-only result intake for controlled run output. This module validates the
shape of a supplied run record and produces an immutable intake decision. It
never writes progress, advances cursors, wakes loops, or starts work.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeExecutionResultIntakeRecord:
    result_intake_authorized: bool
    source_run_bridge_id: str
    result_work_id: str
    result_status: str
    result_payload: dict[str, Any]
    intake_reason: str
    denial_reason: str
    progress_memory_mutated: bool
    cursor_advanced: bool
    scheduler_wake_requested: bool
    runtime_state_mutated: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def evaluate_execution_result_intake(run_bridge_record: Any) -> RuntimeExecutionResultIntakeRecord:
    if run_bridge_record is None:
        return _deny("missing_run_bridge_record")

    authorized = bool(
        _read(run_bridge_record, "controlled_run_authorized", False)
        or _read(run_bridge_record, "run_bridge_authorized", False)
    )
    if not authorized:
        return _deny("run_bridge_not_authorized", run_bridge_record)

    source_id = str(
        _read(run_bridge_record, "run_bridge_id", "")
        or _read(run_bridge_record, "source_activation_id", "")
        or _read(run_bridge_record, "source_handoff_id", "")
    )
    work_id = str(
        _read(run_bridge_record, "run_work_id", "")
        or _read(run_bridge_record, "handoff_work_id", "")
        or _read(run_bridge_record, "work_id", "")
    )
    result_status = str(_read(run_bridge_record, "run_status", "") or _read(run_bridge_record, "result_status", "")).strip().lower()
    payload = _read(run_bridge_record, "run_result", None)
    if payload is None:
        payload = _read(run_bridge_record, "result_payload", {})

    if not source_id:
        return _deny("missing_source_run_bridge_id", run_bridge_record)
    if not work_id:
        return _deny("missing_result_work_id", run_bridge_record)
    if result_status not in {"finished", "failed", "blocked", "cancelled"}:
        return _deny("unsupported_result_status", run_bridge_record)
    if not isinstance(payload, Mapping):
        return _deny("result_payload_not_mapping", run_bridge_record)

    return RuntimeExecutionResultIntakeRecord(
        result_intake_authorized=True,
        source_run_bridge_id=source_id,
        result_work_id=work_id,
        result_status=result_status,
        result_payload=dict(payload),
        intake_reason="run_result_intake_authorized",
        denial_reason="",
        progress_memory_mutated=False,
        cursor_advanced=False,
        scheduler_wake_requested=False,
        runtime_state_mutated=False,
    )


def _deny(reason: str, source: Any = None) -> RuntimeExecutionResultIntakeRecord:
    return RuntimeExecutionResultIntakeRecord(
        result_intake_authorized=False,
        source_run_bridge_id=str(_read(source, "run_bridge_id", "") or _read(source, "source_activation_id", "")),
        result_work_id=str(_read(source, "run_work_id", "") or _read(source, "handoff_work_id", "")),
        result_status=str(_read(source, "run_status", "") or _read(source, "result_status", "")),
        result_payload={},
        intake_reason="",
        denial_reason=reason,
        progress_memory_mutated=False,
        cursor_advanced=False,
        scheduler_wake_requested=False,
        runtime_state_mutated=False,
    )


__all__ = ["RuntimeExecutionResultIntakeRecord", "evaluate_execution_result_intake"]
