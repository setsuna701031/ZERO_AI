"""Runtime executor activation bridge.

The bridge may carry admitted activation data to an injected handler. It does
not own execution, dispatch, queue mutation, or progress mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class RuntimeExecutorActivationBridgeRecord:
    executor_activation_bridge_authorized: bool
    source_activation_admission_id: str
    handoff_work_id: str
    activation_handler_called: bool
    activation_result_received: bool
    activation_result: dict[str, Any]
    execution_started: bool
    runtime_state_mutated: bool
    denial_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_result(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if value is None:
        return {}
    return {"result": value}


def _record(
    *,
    authorized: bool,
    source_activation_admission_id: str = "",
    handoff_work_id: str = "",
    handler_called: bool = False,
    result_received: bool = False,
    result: Any = None,
    denial: str = "",
) -> RuntimeExecutorActivationBridgeRecord:
    return RuntimeExecutorActivationBridgeRecord(
        executor_activation_bridge_authorized=bool(authorized),
        source_activation_admission_id=_text(source_activation_admission_id),
        handoff_work_id=_text(handoff_work_id),
        activation_handler_called=bool(handler_called),
        activation_result_received=bool(result_received),
        activation_result=_safe_result(result),
        execution_started=False,
        runtime_state_mutated=False,
        denial_reason=_text(denial),
    )


def evaluate_executor_activation_bridge(
    activation_admission_record: Any,
    executor_activation_handler: Callable[[dict[str, Any]], Any] | None = None,
) -> RuntimeExecutorActivationBridgeRecord:
    """Carry authorized activation data to an injected handler if provided."""

    if not activation_admission_record:
        return _record(authorized=False, denial="missing_executor_activation_admission_record")

    admitted = bool(_read(activation_admission_record, "executor_activation_admitted", False))
    if not admitted:
        return _record(authorized=False, denial="executor_activation_not_admitted")

    work_id = _text(_read(activation_admission_record, "handoff_work_id", ""))
    if not work_id:
        return _record(authorized=False, denial="missing_handoff_work_id")

    source_id = _text(
        _read(activation_admission_record, "source_handoff_id", "")
        or _read(activation_admission_record, "activation_admission_id", "")
        or _read(activation_admission_record, "id", "")
    )

    if executor_activation_handler is None:
        return _record(
            authorized=True,
            source_activation_admission_id=source_id,
            handoff_work_id=work_id,
        )

    payload = {
        "handoff_work_id": work_id,
        "source_activation_admission_id": source_id,
    }

    try:
        result = executor_activation_handler(payload)
    except Exception:
        return _record(
            authorized=False,
            source_activation_admission_id=source_id,
            handoff_work_id=work_id,
            handler_called=True,
            denial="executor_activation_handler_failed",
        )

    return _record(
        authorized=True,
        source_activation_admission_id=source_id,
        handoff_work_id=work_id,
        handler_called=True,
        result_received=True,
        result=result,
    )


__all__ = [
    "RuntimeExecutorActivationBridgeRecord",
    "evaluate_executor_activation_bridge",
]
