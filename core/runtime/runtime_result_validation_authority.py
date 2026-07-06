"""Runtime result validation authority.

Validates an intake record as data only. Validation does not persist progress,
move cursors, wake orchestration, or invoke any work surface.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeResultValidationRecord:
    result_validation_authorized: bool
    source_result_intake_id: str
    validated_work_id: str
    validated_status: str
    validation_reason: str
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


def evaluate_result_validation(intake_record: Any) -> RuntimeResultValidationRecord:
    if intake_record is None:
        return _deny("missing_intake_record")
    if not bool(_read(intake_record, "result_intake_authorized", False)):
        return _deny("intake_not_authorized", intake_record)

    source_id = str(_read(intake_record, "source_run_bridge_id", ""))
    work_id = str(_read(intake_record, "result_work_id", ""))
    status = str(_read(intake_record, "result_status", "")).strip().lower()

    if not source_id:
        return _deny("missing_source_result_intake_id", intake_record)
    if not work_id:
        return _deny("missing_validated_work_id", intake_record)
    if status not in {"finished", "failed", "blocked", "cancelled"}:
        return _deny("unsupported_validated_status", intake_record)

    return RuntimeResultValidationRecord(
        result_validation_authorized=True,
        source_result_intake_id=source_id,
        validated_work_id=work_id,
        validated_status=status,
        validation_reason="result_validation_authorized",
        denial_reason="",
        progress_memory_mutated=False,
        cursor_advanced=False,
        scheduler_wake_requested=False,
        runtime_state_mutated=False,
    )


def _deny(reason: str, source: Any = None) -> RuntimeResultValidationRecord:
    return RuntimeResultValidationRecord(
        result_validation_authorized=False,
        source_result_intake_id=str(_read(source, "source_run_bridge_id", "")),
        validated_work_id=str(_read(source, "result_work_id", "")),
        validated_status=str(_read(source, "result_status", "")),
        validation_reason="",
        denial_reason=reason,
        progress_memory_mutated=False,
        cursor_advanced=False,
        scheduler_wake_requested=False,
        runtime_state_mutated=False,
    )


__all__ = ["RuntimeResultValidationRecord", "evaluate_result_validation"]
