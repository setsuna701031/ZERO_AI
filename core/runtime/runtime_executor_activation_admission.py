"""Runtime executor activation admission.

This module admits executor activation from a prior handoff record, but it
never starts execution and never mutates runtime state.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeExecutorActivationAdmissionRecord:
    executor_activation_admitted: bool
    source_handoff_id: str
    handoff_work_id: str
    activation_reason: str
    denial_reason: str
    executor_called: bool
    execution_started: bool
    runtime_state_mutated: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _record(
    *,
    admitted: bool,
    source_handoff_id: str = "",
    handoff_work_id: str = "",
    reason: str = "",
    denial: str = "",
) -> RuntimeExecutorActivationAdmissionRecord:
    return RuntimeExecutorActivationAdmissionRecord(
        executor_activation_admitted=bool(admitted),
        source_handoff_id=_text(source_handoff_id),
        handoff_work_id=_text(handoff_work_id),
        activation_reason=_text(reason),
        denial_reason=_text(denial),
        executor_called=False,
        execution_started=False,
        runtime_state_mutated=False,
    )


def evaluate_executor_activation_admission(
    executor_handoff_record: Any,
    activation_mode: Any = None,
) -> RuntimeExecutorActivationAdmissionRecord:
    """Admit executor activation from a valid handoff record only."""

    del activation_mode

    if not executor_handoff_record:
        return _record(admitted=False, denial="missing_executor_handoff_record")

    authorized = bool(_read(executor_handoff_record, "executor_handoff_authorized", False))
    if not authorized:
        return _record(admitted=False, denial="executor_handoff_not_authorized")

    work_id = _text(_read(executor_handoff_record, "handoff_work_id", ""))
    if not work_id:
        return _record(admitted=False, denial="missing_handoff_work_id")

    source_handoff_id = _text(
        _read(executor_handoff_record, "source_selection_id", "")
        or _read(executor_handoff_record, "handoff_id", "")
        or _read(executor_handoff_record, "id", "")
    )

    return _record(
        admitted=True,
        source_handoff_id=source_handoff_id,
        handoff_work_id=work_id,
        reason="executor_activation_admitted_from_handoff",
    )


__all__ = [
    "RuntimeExecutorActivationAdmissionRecord",
    "evaluate_executor_activation_admission",
]
