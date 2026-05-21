from __future__ import annotations

from typing import Any


def runtime_topology_summary(
    *,
    state: dict[str, Any] | None = None,
    journal: Any = None,
    transaction_coordinator: Any = None,
    capability_graph: dict[str, Any] | None = None,
    intent_governance: dict[str, Any] | None = None,
    replay_artifact: dict[str, Any] | None = None,
    evidence_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    records = journal.replay_records() if journal is not None and hasattr(journal, "replay_records") else []
    scopes = getattr(transaction_coordinator, "_scopes", {}) if transaction_coordinator is not None else {}
    return {
        "state": dict(state or {}),
        "journal": {
            "record_count": len(records),
            "record_types": sorted({record.record_type for record in records}),
        },
        "transactions": {
            "count": len(scopes),
            "open": [scope.transaction_id for scope in scopes.values() if not scope.is_closed],
            "closed": [scope.transaction_id for scope in scopes.values() if scope.is_closed],
        },
        "capability_nodes": sorted((capability_graph or {}).get("nodes", {}).keys()),
        "intent": dict(intent_governance or {}),
        "replay": {
            "replay_id": (replay_artifact or {}).get("replay_id", ""),
            "replayable": bool((replay_artifact or {}).get("replayable", False)),
        },
        "evidence": {
            "bundle_id": (evidence_bundle or {}).get("bundle_id", ""),
            "sealed": bool((evidence_bundle or {}).get("runtime_seal")),
        },
    }


__all__ = ["runtime_topology_summary"]
