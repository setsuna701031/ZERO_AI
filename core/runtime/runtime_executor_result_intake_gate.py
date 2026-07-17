"""Runtime executor result intake gate.

This gate accepts activation handler results as data. It does not mark runtime
state, mutate queues, or start execution.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeExecutorResultIntakeRecord:
    executor_result_intake_authorized: bool
    source_activation_bridge_id: str
    handoff_work_id: str
    result_accepted: bool
    terminal_status: str
    denial_reason: str
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
    authorized: bool,
    source_activation_bridge_id: str = "",
    handoff_work_id: str = "",
    accepted: bool = False,
    status: str = "",
    denial: str = "",
) -> RuntimeExecutorResultIntakeRecord:
    return RuntimeExecutorResultIntakeRecord(
        executor_result_intake_authorized=bool(authorized),
        source_activation_bridge_id=_text(source_activation_bridge_id),
        handoff_work_id=_text(handoff_work_id),
        result_accepted=bool(accepted),
        terminal_status=_text(status),
        denial_reason=_text(denial),
        execution_started=False,
        runtime_state_mutated=False,
    )


def evaluate_executor_result_intake(
    activation_bridge_record: Any,
) -> RuntimeExecutorResultIntakeRecord:
    """Authorize data intake from an activation bridge result."""

    if not activation_bridge_record:
        return _record(authorized=False, denial="missing_executor_activation_bridge_record")

    bridge_authorized = bool(
        _read(activation_bridge_record, "executor_activation_bridge_authorized", False)
    )
    if not bridge_authorized:
        return _record(authorized=False, denial="executor_activation_bridge_not_authorized")

    work_id = _text(_read(activation_bridge_record, "handoff_work_id", ""))
    if not work_id:
        return _record(authorized=False, denial="missing_handoff_work_id")

    result_received = bool(_read(activation_bridge_record, "activation_result_received", False))
    if not result_received:
        return _record(
            authorized=False,
            source_activation_bridge_id=_text(
                _read(activation_bridge_record, "source_activation_admission_id", "")
            ),
            handoff_work_id=work_id,
            denial="missing_activation_result",
        )

    result = _read(activation_bridge_record, "activation_result", {})
    status = "accepted"
    if isinstance(result, Mapping):
        status = _text(result.get("status", "accepted")) or "accepted"

    return _record(
        authorized=True,
        source_activation_bridge_id=_text(
            _read(activation_bridge_record, "source_activation_admission_id", "")
        ),
        handoff_work_id=work_id,
        accepted=True,
        status=status,
    )


__all__ = [
    "RuntimeExecutorResultIntakeRecord",
    "evaluate_executor_result_intake",
]
