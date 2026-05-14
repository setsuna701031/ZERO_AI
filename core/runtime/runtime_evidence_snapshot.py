from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.runtime_evidence_registry import (
    RuntimeEvidenceRegistry,
    RuntimeEvidenceRegistrySnapshot,
)


class RuntimeEvidenceSnapshot:
    SCHEMA = "zero.runtime_evidence.snapshot.v1"

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = self._json_safe(payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return str(self._payload.get("fingerprint") or "")

    def export(self) -> dict[str, Any]:
        return self.payload

    def export_execution(self, execution_id: str | None = None) -> dict[str, Any]:
        executions = self._payload.get("executions")
        if not isinstance(executions, dict):
            executions = {}
        if execution_id is None:
            return {
                "schema": "zero.runtime_evidence.execution_snapshot.v1",
                "execution_count": len(executions),
                "executions": copy.deepcopy(executions),
            }
        execution_id = str(execution_id)
        execution = executions.get(execution_id)
        return {
            "schema": "zero.runtime_evidence.execution_snapshot.v1",
            "found": isinstance(execution, dict),
            "execution_id": execution_id,
            "execution": copy.deepcopy(execution) if isinstance(execution, dict) else {},
        }

    def export_lineage(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("lineage_snapshot", {}))

    def export_replay(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("replay_snapshot", {}))

    def export_rollback(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("rollback_snapshot", {}))

    def export_failed_executions(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("failed_execution_snapshot", {}))

    def export_sealed_state(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("sealed_state_snapshot", {}))

    def export_events(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("event_snapshot", {}))

    def _json_safe(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {}
        encoded = json.dumps(
            payload,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return json.loads(encoded)


class RuntimeEvidenceSnapshotBuilder:
    def __init__(self, registry: RuntimeEvidenceRegistry | None = None) -> None:
        self.registry = registry if registry is not None else RuntimeEvidenceRegistry()

    def build(self, source: Any) -> RuntimeEvidenceSnapshot:
        registry_snapshot = self._registry_snapshot(source)
        registry_payload = registry_snapshot.payload

        payload = {
            "ok": True,
            "schema": RuntimeEvidenceSnapshot.SCHEMA,
            "registry_fingerprint": registry_snapshot.fingerprint,
            "summary_fingerprint": self._safe_text(registry_payload.get("summary_fingerprint")),
            "record_refs": self._safe_mapping(registry_payload.get("record_refs")),
            "sealed_state_snapshot": self._sealed_state_snapshot(registry_payload),
            "executions": self._execution_snapshot(registry_payload),
            "lineage_snapshot": self._lineage_snapshot(registry_payload),
            "replay_snapshot": self._replay_snapshot(registry_payload),
            "rollback_snapshot": self._rollback_snapshot(registry_payload),
            "failed_execution_snapshot": self._failed_execution_snapshot(registry_payload),
            "event_snapshot": self._event_snapshot(registry_payload),
            "snapshot_counts": self._snapshot_counts(registry_payload),
        }
        payload["fingerprint"] = self._fingerprint(payload)
        return RuntimeEvidenceSnapshot(payload)

    def _registry_snapshot(self, source: Any) -> RuntimeEvidenceRegistrySnapshot:
        if isinstance(source, RuntimeEvidenceRegistrySnapshot):
            return RuntimeEvidenceRegistrySnapshot(source.payload)
        if isinstance(source, RuntimeEvidenceSnapshot):
            payload = source.payload
            registry_payload = {
                "ok": bool(payload.get("ok", False)),
                "schema": RuntimeEvidenceRegistrySnapshot.SCHEMA,
                "sealed": bool(
                    self._safe_mapping(payload.get("sealed_state_snapshot")).get("sealed", False)
                ),
                "sealed_state": self._safe_mapping(payload.get("sealed_state_snapshot")),
                "summary_fingerprint": self._safe_text(payload.get("summary_fingerprint")),
                "record_refs": self._safe_mapping(payload.get("record_refs")),
                "execution_index": self._safe_mapping(payload.get("executions")),
                "step_index": {},
                "lineage_index": self._safe_mapping(
                    self._safe_mapping(payload.get("lineage_snapshot")).get("lineage_index")
                ),
                "replay_index": self._safe_mapping(
                    self._safe_mapping(payload.get("replay_snapshot")).get("replay_index")
                ),
                "rollback_index": self._safe_mapping(
                    self._safe_mapping(payload.get("rollback_snapshot")).get("rollback_index")
                ),
                "failed_execution_index": self._safe_list(
                    self._safe_mapping(payload.get("failed_execution_snapshot")).get("failed_executions")
                ),
                "event_index": self._safe_list(
                    self._safe_mapping(payload.get("event_snapshot")).get("events")
                ),
                "index_counts": self._safe_mapping(payload.get("snapshot_counts")),
            }
            registry_payload["fingerprint"] = self._fingerprint(registry_payload)
            return RuntimeEvidenceRegistrySnapshot(registry_payload)
        return self.registry.rebuild(source)

    def _sealed_state_snapshot(self, registry_payload: dict[str, Any]) -> dict[str, Any]:
        sealed_state = self._safe_mapping(registry_payload.get("sealed_state"))
        return {
            "schema": "zero.runtime_evidence.sealed_state_snapshot.v1",
            "sealed": bool(registry_payload.get("sealed", False)),
            "complete": bool(sealed_state.get("complete", False)),
            "reason": self._safe_text(sealed_state.get("reason")),
            "missing_records": self._safe_list(sealed_state.get("missing_records")),
            "record_count": self._safe_int(sealed_state.get("record_count"), 0),
            "seal_id": self._safe_text(sealed_state.get("seal_id")),
            "seal_fingerprint": self._safe_text(sealed_state.get("seal_fingerprint")),
        }

    def _execution_snapshot(self, registry_payload: dict[str, Any]) -> dict[str, Any]:
        execution_index = self._safe_mapping(registry_payload.get("execution_index"))
        return {
            key: {
                "execution_id": self._safe_text(value.get("execution_id")),
                "execution_index": value.get("execution_index"),
                "aggregate_status": self._safe_text(value.get("aggregate_status")),
                "record_refs": self._safe_mapping(value.get("record_refs")),
            }
            for key, value in sorted(execution_index.items())
            if isinstance(value, dict)
        }

    def _lineage_snapshot(self, registry_payload: dict[str, Any]) -> dict[str, Any]:
        lineage_index = self._safe_mapping(registry_payload.get("lineage_index"))
        lineage_nodes = [
            {
                "lineage_id": self._safe_text(value.get("lineage_id")),
                "lineage_type": self._safe_text(value.get("lineage_type")),
                "lineage_index": value.get("lineage_index"),
                "verified": bool(value.get("verified", False)),
            }
            for _, value in sorted(
                lineage_index.items(),
                key=lambda item: self._safe_int(
                    item[1].get("lineage_index") if isinstance(item[1], dict) else 0,
                    0,
                ),
            )
            if isinstance(value, dict)
        ]
        return {
            "schema": "zero.runtime_evidence.lineage_snapshot.v1",
            "lineage_count": len(lineage_nodes),
            "lineage": lineage_nodes,
            "lineage_index": {
                item["lineage_id"]: copy.deepcopy(item)
                for item in lineage_nodes
                if item["lineage_id"]
            },
        }

    def _replay_snapshot(self, registry_payload: dict[str, Any]) -> dict[str, Any]:
        replay_index = self._safe_mapping(registry_payload.get("replay_index"))
        return {
            "schema": "zero.runtime_evidence.replay_snapshot.v1",
            "replay_count": len(replay_index),
            "replay_index": self._ordered_mapping(replay_index),
        }

    def _rollback_snapshot(self, registry_payload: dict[str, Any]) -> dict[str, Any]:
        rollback_index = self._safe_mapping(registry_payload.get("rollback_index"))
        return {
            "schema": "zero.runtime_evidence.rollback_snapshot.v1",
            "rollback_count": len(rollback_index),
            "rollback_index": self._ordered_mapping(rollback_index),
        }

    def _failed_execution_snapshot(self, registry_payload: dict[str, Any]) -> dict[str, Any]:
        failed = self._safe_list(registry_payload.get("failed_execution_index"))
        safe_failed = [
            {
                "failed_execution_id": self._safe_text(item.get("failed_execution_id")),
                "source": self._safe_text(item.get("source")),
                "event_index": item.get("event_index"),
                "phase": self._safe_text(item.get("phase")),
                "status": self._safe_text(item.get("status")),
                "fingerprint": self._safe_text(item.get("fingerprint")),
            }
            for item in failed
            if isinstance(item, dict)
        ]
        return {
            "schema": "zero.runtime_evidence.failed_execution_snapshot.v1",
            "failed": bool(safe_failed),
            "failed_execution_count": len(safe_failed),
            "failed_executions": safe_failed,
        }

    def _event_snapshot(self, registry_payload: dict[str, Any]) -> dict[str, Any]:
        events = self._safe_list(registry_payload.get("event_index"))
        safe_events = [
            {
                "event_order": index,
                "event_key": self._safe_text(item.get("event_key")),
                "layer": self._safe_text(item.get("layer")),
                "event_index": item.get("event_index"),
                "phase": self._safe_text(item.get("phase")),
                "status": self._safe_text(item.get("status")),
                "fingerprint": self._safe_text(item.get("fingerprint")),
            }
            for index, item in enumerate(events)
            if isinstance(item, dict)
        ]
        return {
            "schema": "zero.runtime_evidence.event_snapshot.v1",
            "event_count": len(safe_events),
            "events": safe_events,
        }

    def _snapshot_counts(self, registry_payload: dict[str, Any]) -> dict[str, int]:
        counts = self._safe_mapping(registry_payload.get("index_counts"))
        return {
            "executions": self._safe_int(counts.get("executions"), 0),
            "lineage": self._safe_int(counts.get("lineage"), 0),
            "replay": self._safe_int(counts.get("replay"), 0),
            "rollback": self._safe_int(counts.get("rollback"), 0),
            "failed_executions": self._safe_int(counts.get("failed_executions"), 0),
            "events": self._safe_int(counts.get("events"), 0),
        }

    def _ordered_mapping(self, value: dict[str, Any]) -> dict[str, Any]:
        return {
            key: copy.deepcopy(value[key])
            for key in sorted(value)
        }

    def _safe_mapping(self, value: Any) -> dict[str, Any]:
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    def _safe_list(self, value: Any) -> list[Any]:
        return copy.deepcopy(value) if isinstance(value, list) else []

    def _safe_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    def _fingerprint(self, payload: dict[str, Any]) -> str:
        safe = copy.deepcopy(payload)
        safe.pop("fingerprint", None)
        encoded = json.dumps(
            safe,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_runtime_evidence_snapshot(source: Any) -> RuntimeEvidenceSnapshot:
    return RuntimeEvidenceSnapshotBuilder().build(source)


__all__ = [
    "RuntimeEvidenceSnapshot",
    "RuntimeEvidenceSnapshotBuilder",
    "build_runtime_evidence_snapshot",
]
