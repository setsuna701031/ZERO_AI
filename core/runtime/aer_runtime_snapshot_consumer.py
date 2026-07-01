"""Pure Runtime Snapshot v1 consumer boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_snapshot import SNAPSHOT_CONTRACT as _SNAPSHOT_CONTRACT
from core.runtime.aer_runtime_snapshot import validate_snapshot as _validate_snapshot


_CONSUMER_RESULT_CONTRACT = "aer.runtime.snapshot.consumer_result.v1"


def consume_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Inspect a Snapshot v1 payload as a descriptive consumer result."""

    validation = _validate_snapshot(snapshot)
    accepted = validation["valid"] is True and _mapping_get(snapshot, "contract") == _SNAPSHOT_CONTRACT
    reason = "accepted" if accepted else validation["reason"]

    return {
        "contract": _CONSUMER_RESULT_CONTRACT,
        "accepted": accepted,
        "rejected": not accepted,
        "status": "accepted" if accepted else "rejected",
        "reason": reason,
        "snapshot_contract": _text_or_none(_mapping_get(snapshot, "contract")),
        "snapshot_id": _text_or_none(_mapping_get(snapshot, "snapshot_id")),
        "lineage": _lineage(snapshot),
        "validation": validation,
        "descriptive_only": True,
    }


def snapshot_consumer_to_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """Project a consumer result to a minimal public summary."""

    accepted = result.get("accepted") is True
    return {
        "contract": _CONSUMER_RESULT_CONTRACT,
        "accepted": accepted,
        "rejected": not accepted,
        "status": "accepted" if accepted else "rejected",
        "reason": result.get("reason"),
        "snapshot_contract": result.get("snapshot_contract"),
        "snapshot_id": result.get("snapshot_id"),
        "lineage": _lineage(result.get("lineage", {})),
    }


def _lineage(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: value[key]
        for key in ("source_valid", "source_outcome", "source_status")
        if key in value
    }


def _text_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _mapping_get(value: Any, key: str) -> Any:
    if not isinstance(value, Mapping):
        return None
    return value.get(key)


__all__ = [
    "consume_snapshot",
    "snapshot_consumer_to_summary",
]
