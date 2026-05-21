from __future__ import annotations

from typing import Any

from core.runtime.runtime_abi import abi_manifest
from core.runtime.runtime_compatibility import check_runtime_compatibility
from core.runtime.runtime_integrity import verify_integrity
from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_seal import verify_runtime_seal
from core.runtime.runtime_version import runtime_version_descriptor


def runtime_diagnostics(
    *,
    journal: RuntimeJournal | None = None,
    transaction_coordinator: Any = None,
    replay_artifact: dict[str, Any] | None = None,
    evidence_bundle: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    event_bus: Any = None,
    memory_snapshots: list[dict[str, Any]] | None = None,
    isolation_boundary: dict[str, Any] | None = None,
    capability_graph: dict[str, Any] | None = None,
    intent_governance: dict[str, Any] | None = None,
    scheduler: dict[str, Any] | None = None,
) -> dict[str, Any]:
    wal = journal.reconstruct() if journal is not None else {"records": []}
    wal_reports = [verify_integrity(record, artifact_type="runtime_wal_record").to_dict() for record in wal.get("records", [])]
    replay_payload = dict(replay_artifact or {})
    evidence_payload = dict(evidence_bundle or {})
    return {
        "runtime": runtime_version_descriptor().to_dict(),
        "state": dict(state or {}),
        "event_bus": _event_bus_summary(event_bus),
        "wal": {
            "record_count": wal.get("record_count", len(wal.get("records", []))),
            "last_sequence": wal.get("last_sequence", 0),
            "integrity": wal_reports,
        },
        "transactions": _transaction_summary(transaction_coordinator),
        "memory_snapshots": list(memory_snapshots or []),
        "isolation_boundary": dict(isolation_boundary or {}),
        "capability_graph": dict(capability_graph or {}),
        "intent_governance": dict(intent_governance or {}),
        "scheduler": dict(scheduler or {}),
        "replay": {
            "present": bool(replay_payload),
            "integrity": verify_runtime_seal(replay_payload, artifact_type="runtime_replay_artifact").to_dict() if replay_payload else {},
            "compatibility": check_runtime_compatibility(replay_payload, artifact_type="runtime_replay_artifact").to_dict() if replay_payload else {},
        },
        "evidence": {
            "present": bool(evidence_payload),
            "integrity": verify_runtime_seal(evidence_payload, artifact_type="runtime_evidence_bundle").to_dict() if evidence_payload else {},
            "compatibility": check_runtime_compatibility(evidence_payload, artifact_type="runtime_evidence_bundle").to_dict() if evidence_payload else {},
        },
        "abi": abi_manifest(),
    }


def _event_bus_summary(event_bus: Any) -> dict[str, Any]:
    if event_bus is None or not hasattr(event_bus, "get_events"):
        return {"event_count": 0, "events": []}
    events = event_bus.get_events()
    return {
        "event_count": len(events),
        "events": [
            {
                "channel": event.channel,
                "event_type": event.event_type,
                "sequence": event.sequence,
                "timestamp": event.timestamp,
            }
            for event in events
        ],
    }


def _transaction_summary(transaction_coordinator: Any) -> dict[str, Any]:
    if transaction_coordinator is None:
        return {"count": 0, "transactions": []}
    scopes = getattr(transaction_coordinator, "_scopes", {})
    snapshots = getattr(transaction_coordinator, "_snapshots", {})
    return {
        "count": len(scopes),
        "transactions": [scope.to_metadata() for scope in scopes.values()],
        "snapshots": [snapshot.to_metadata() for snapshot in snapshots.values()],
    }


__all__ = ["runtime_diagnostics"]
