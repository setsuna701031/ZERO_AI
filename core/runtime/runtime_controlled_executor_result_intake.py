"""Controlled run result intake gate."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_SCHEMA = "zero.runtime.controlled_run_result_intake.v1"


def _rec(**values: Any) -> dict[str, Any]:
    base = {
        "schema": _SCHEMA,
        "record_type": "RuntimeControlledRunResultIntakeRecord",
        "result_intake_authorized": False,
        "source_run_bridge_id": None,
        "run_result_id": None,
        "run_status": None,
        "result_payload_accepted": False,
        "progress_apply_requested": False,
        "cursor_advanced": False,
        "runtime_state_mutated": False,
        "denial_reason": None,
    }
    base.update(values)
    return base


def evaluate_controlled_run_result_intake(
    run_bridge_record: Mapping[str, Any] | None,
    result_policy: str | None = None,
) -> dict[str, Any]:
    """Accept a controlled run result as data only."""
    if not isinstance(run_bridge_record, Mapping):
        return _rec(denial_reason="missing_run_bridge_record")

    bridge_ok = bool(run_bridge_record.get("controlled_run_bridge_authorized"))
    result_received = bool(run_bridge_record.get("run_result_received"))
    result_id = run_bridge_record.get("run_result_id")
    status = run_bridge_record.get("run_status")
    source_id = run_bridge_record.get("source_run_admission_id")

    if not bridge_ok:
        return _rec(
            source_run_bridge_id=source_id,
            run_result_id=result_id,
            run_status=status,
            denial_reason="run_bridge_not_authorized",
        )

    if not result_received:
        return _rec(
            source_run_bridge_id=source_id,
            run_status=status,
            denial_reason="missing_run_result",
        )

    if not result_id:
        return _rec(
            source_run_bridge_id=source_id,
            run_status=status,
            denial_reason="missing_run_result_id",
        )

    return _rec(
        result_intake_authorized=True,
        source_run_bridge_id=source_id,
        run_result_id=result_id,
        run_status=status,
        result_payload_accepted=True,
        denial_reason=None,
    )


__all__ = ["evaluate_controlled_run_result_intake"]
