"""Runtime result to progress-apply adapter.

Transforms validated result data into a progress-apply candidate record. The
adapter only prepares data for downstream apply authorization and never commits
progress, moves cursors, or requests another tick.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeResultProgressApplyCandidate:
    progress_apply_candidate_created: bool
    source_validation_id: str
    progress_work_id: str
    progress_status: str
    candidate_reason: str
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


def build_progress_apply_candidate(validation_record: Any) -> RuntimeResultProgressApplyCandidate:
    if validation_record is None:
        return _deny("missing_validation_record")
    if not bool(_read(validation_record, "result_validation_authorized", False)):
        return _deny("validation_not_authorized", validation_record)

    source_id = str(_read(validation_record, "source_result_intake_id", ""))
    work_id = str(_read(validation_record, "validated_work_id", ""))
    status = str(_read(validation_record, "validated_status", "")).strip().lower()

    if not source_id:
        return _deny("missing_source_validation_id", validation_record)
    if not work_id:
        return _deny("missing_progress_work_id", validation_record)
    if status not in {"finished", "failed", "blocked", "cancelled"}:
        return _deny("unsupported_progress_status", validation_record)

    return RuntimeResultProgressApplyCandidate(
        progress_apply_candidate_created=True,
        source_validation_id=source_id,
        progress_work_id=work_id,
        progress_status=status,
        candidate_reason="progress_apply_candidate_created",
        denial_reason="",
        progress_memory_mutated=False,
        cursor_advanced=False,
        scheduler_wake_requested=False,
        runtime_state_mutated=False,
    )


def _deny(reason: str, source: Any = None) -> RuntimeResultProgressApplyCandidate:
    return RuntimeResultProgressApplyCandidate(
        progress_apply_candidate_created=False,
        source_validation_id=str(_read(source, "source_result_intake_id", "")),
        progress_work_id=str(_read(source, "validated_work_id", "")),
        progress_status=str(_read(source, "validated_status", "")),
        candidate_reason="",
        denial_reason=reason,
        progress_memory_mutated=False,
        cursor_advanced=False,
        scheduler_wake_requested=False,
        runtime_state_mutated=False,
    )


__all__ = ["RuntimeResultProgressApplyCandidate", "build_progress_apply_candidate"]
