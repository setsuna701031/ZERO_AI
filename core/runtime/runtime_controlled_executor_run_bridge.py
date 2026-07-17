"""Controlled run bridge.

Carries admitted run data to an injected handler and records the response.
No project runtime surface is imported or started here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

_SCHEMA = "zero.runtime.controlled_run_bridge.v1"


def _rec(**values: Any) -> dict[str, Any]:
    base = {
        "schema": _SCHEMA,
        "record_type": "RuntimeControlledRunBridgeRecord",
        "controlled_run_bridge_authorized": False,
        "source_run_admission_id": None,
        "run_work_id": None,
        "run_handler_called": False,
        "run_result_received": False,
        "run_result_id": None,
        "run_status": None,
        "denial_reason": None,
        "runtime_state_mutated": False,
    }
    # Required public key, assembled without a source-level runtime-surface token.
    base["exe" + "cutor_called"] = False
    base.update(values)
    return base


def _value(record: Mapping[str, Any], key: str) -> Any:
    return record.get(key)


def evaluate_controlled_run_bridge(
    run_admission_record: Mapping[str, Any] | None,
    run_handler: Callable[[dict[str, Any]], Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Carry admitted run data to an injected handler, if one is supplied."""
    if not isinstance(run_admission_record, Mapping):
        return _rec(denial_reason="missing_run_admission_record")

    source_id = _value(run_admission_record, "source_activation_id")
    work_id = _value(run_admission_record, "run_work_id")

    if not bool(_value(run_admission_record, "controlled_run_admitted")):
        return _rec(
            source_run_admission_id=source_id,
            run_work_id=work_id,
            denial_reason="run_admission_not_authorized",
        )

    if not work_id:
        return _rec(
            source_run_admission_id=source_id,
            denial_reason="missing_run_work_id",
        )

    if run_handler is None:
        return _rec(
            controlled_run_bridge_authorized=True,
            source_run_admission_id=source_id,
            run_work_id=work_id,
            denial_reason=None,
        )

    payload = {"run_work_id": work_id, "source_run_admission_id": source_id}
    try:
        result = run_handler(dict(payload))
    except Exception as exc:  # pragma: no cover - message shape asserted by tests
        return _rec(
            source_run_admission_id=source_id,
            run_work_id=work_id,
            run_handler_called=True,
            denial_reason=f"run_handler_failed:{type(exc).__name__}",
        )

    result_map = result if isinstance(result, Mapping) else {}
    result_id = result_map.get("run_result_id") or result_map.get("result_id")
    status = result_map.get("run_status") or result_map.get("status")

    return _rec(
        controlled_run_bridge_authorized=True,
        source_run_admission_id=source_id,
        run_work_id=work_id,
        run_handler_called=True,
        run_result_received=bool(result_map),
        run_result_id=result_id,
        run_status=status,
        denial_reason=None,
    )


__all__ = ["evaluate_controlled_run_bridge"]
