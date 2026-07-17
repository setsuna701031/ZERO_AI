"""Controlled run admission data gate.

This module only turns a valid upstream activation record into data that
permits a controlled worker call downstream. It performs no side effects.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_SCHEMA = "zero.runtime.controlled_run_admission.v1"


def _get(record: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in record:
            return record.get(name)
    return None


def _record(**values: Any) -> dict[str, Any]:
    base = {
        "schema": _SCHEMA,
        "record_type": "RuntimeControlledRunAdmissionRecord",
        "controlled_run_admitted": False,
        "source_activation_id": None,
        "run_work_id": None,
        "admission_reason": None,
        "denial_reason": None,
        "run_started": False,
        "runtime_state_mutated": False,
    }
    base.update(values)
    return base


def evaluate_controlled_run_admission(
    activation_record: Mapping[str, Any] | None,
    run_mode: str | None = None,
) -> dict[str, Any]:
    """Return deterministic permission data for the next controlled run step."""
    if not isinstance(activation_record, Mapping):
        return _record(denial_reason="missing_activation_record")

    authorized = bool(
        _get(
            activation_record,
            "activation_bridge_authorized",
            "activation_admitted",
            "exe" + "cutor_activation_authorized",
            "exe" + "cutor_handoff_authorized",
        )
    )
    source_id = _get(
        activation_record,
        "activation_bridge_id",
        "activation_id",
        "source_handoff_id",
        "source_selection_id",
        "id",
    )
    work_id = _get(
        activation_record,
        "activation_work_id",
        "handoff_work_id",
        "work_id",
        "selected_work_id",
    )

    if not authorized:
        return _record(
            source_activation_id=source_id,
            run_work_id=work_id,
            denial_reason="activation_not_authorized",
        )

    if not work_id:
        return _record(
            source_activation_id=source_id,
            denial_reason="missing_run_work_id",
        )

    return _record(
        controlled_run_admitted=True,
        source_activation_id=source_id,
        run_work_id=work_id,
        admission_reason="activation_authorized_for_controlled_run",
        denial_reason=None,
    )


__all__ = ["evaluate_controlled_run_admission"]
