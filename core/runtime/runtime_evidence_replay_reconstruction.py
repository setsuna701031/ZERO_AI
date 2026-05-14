from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.runtime_evidence_snapshot import (
    RuntimeEvidenceSnapshot,
    RuntimeEvidenceSnapshotBuilder,
)


class RuntimeEvidenceReplayState:
    SCHEMA = "zero.runtime_evidence.replay_reconstruction.v1"

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

    def execution_replay(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("execution_replay", []))

    def lineage_replay(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("lineage_replay", []))

    def failed_execution_replay(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("failed_execution_replay", []))

    def rollback_replay(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("rollback_replay", {}))

    def event_replay_order(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("event_replay_order", []))

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


class RuntimeEvidenceReplayReconstructor:
    def __init__(self, snapshot_builder: RuntimeEvidenceSnapshotBuilder | None = None) -> None:
        self.snapshot_builder = snapshot_builder if snapshot_builder is not None else RuntimeEvidenceSnapshotBuilder()

    def reconstruct(self, source: Any) -> RuntimeEvidenceReplayState:
        snapshot = self._snapshot_from(source)
        snapshot_payload = snapshot.export()
        payload = {
            "ok": True,
            "schema": RuntimeEvidenceReplayState.SCHEMA,
            "snapshot_fingerprint": snapshot.fingerprint,
            "sealed_state": snapshot.export_sealed_state(),
            "record_refs": self._safe_mapping(snapshot_payload.get("record_refs")),
            "execution_replay": self._execution_replay(snapshot),
            "lineage_replay": self._lineage_replay(snapshot),
            "failed_execution_replay": self._failed_execution_replay(snapshot),
            "rollback_replay": self._rollback_replay(snapshot),
            "replay_linkage": self._replay_linkage(snapshot),
            "event_replay_order": self._event_replay_order(snapshot),
        }
        payload["replay_counts"] = {
            "executions": len(payload["execution_replay"]),
            "lineage": len(payload["lineage_replay"]),
            "failed_executions": len(payload["failed_execution_replay"]),
            "rollback_steps": len(payload["rollback_replay"].get("rollback_steps", [])),
            "events": len(payload["event_replay_order"]),
        }
        payload["fingerprint"] = self._fingerprint(payload)
        return RuntimeEvidenceReplayState(payload)

    def _snapshot_from(self, source: Any) -> RuntimeEvidenceSnapshot:
        if isinstance(source, RuntimeEvidenceSnapshot):
            return RuntimeEvidenceSnapshot(source.export())
        return self.snapshot_builder.build(source)

    def _execution_replay(self, snapshot: RuntimeEvidenceSnapshot) -> list[dict[str, Any]]:
        execution_snapshot = snapshot.export_execution()
        executions = self._safe_mapping(execution_snapshot.get("executions"))
        ordered = sorted(
            [
                value
                for value in executions.values()
                if isinstance(value, dict)
            ],
            key=lambda item: (
                self._safe_int(item.get("execution_index"), 10**9),
                self._safe_text(item.get("execution_id")),
            ),
        )
        return [
            {
                "replay_order": index,
                "execution_id": self._safe_text(item.get("execution_id")),
                "execution_index": item.get("execution_index"),
                "aggregate_status": self._safe_text(item.get("aggregate_status")),
                "record_refs": self._safe_mapping(item.get("record_refs")),
            }
            for index, item in enumerate(ordered)
        ]

    def _lineage_replay(self, snapshot: RuntimeEvidenceSnapshot) -> list[dict[str, Any]]:
        lineage_snapshot = snapshot.export_lineage()
        lineage = lineage_snapshot.get("lineage")
        if not isinstance(lineage, list):
            lineage = []
        ordered = sorted(
            [
                item
                for item in lineage
                if isinstance(item, dict)
            ],
            key=lambda item: (
                self._safe_int(item.get("lineage_index"), 10**9),
                self._safe_text(item.get("lineage_id")),
            ),
        )
        return [
            {
                "replay_order": index,
                "lineage_id": self._safe_text(item.get("lineage_id")),
                "lineage_type": self._safe_text(item.get("lineage_type")),
                "lineage_index": item.get("lineage_index"),
                "verified": bool(item.get("verified", False)),
            }
            for index, item in enumerate(ordered)
        ]

    def _failed_execution_replay(self, snapshot: RuntimeEvidenceSnapshot) -> list[dict[str, Any]]:
        failed_snapshot = snapshot.export_failed_executions()
        failed = failed_snapshot.get("failed_executions")
        if not isinstance(failed, list):
            failed = []
        return [
            {
                "replay_order": index,
                "failed_execution_id": self._safe_text(item.get("failed_execution_id")),
                "source": self._safe_text(item.get("source")),
                "event_index": item.get("event_index"),
                "phase": self._safe_text(item.get("phase")),
                "status": self._safe_text(item.get("status")),
                "fingerprint": self._safe_text(item.get("fingerprint")),
            }
            for index, item in enumerate(failed)
            if isinstance(item, dict)
        ]

    def _rollback_replay(self, snapshot: RuntimeEvidenceSnapshot) -> dict[str, Any]:
        rollback_snapshot = snapshot.export_rollback()
        rollback_index = self._safe_mapping(rollback_snapshot.get("rollback_index"))
        if not rollback_index:
            return {
                "found": False,
                "rollback_id": "",
                "verified": False,
                "rollback_steps": [],
            }
        rollback_id = sorted(rollback_index)[0]
        rollback = self._safe_mapping(rollback_index.get(rollback_id))
        rollback_order = [
            self._safe_text(item)
            for item in rollback.get("rollback_order", [])
            if self._safe_text(item)
        ] if isinstance(rollback.get("rollback_order"), list) else []
        return {
            "found": True,
            "rollback_id": self._safe_text(rollback.get("rollback_id")),
            "snapshot_id": self._safe_text(rollback.get("snapshot_id")),
            "bundle_id": self._safe_text(rollback.get("bundle_id")),
            "verified": bool(rollback.get("verified", False)),
            "rollback_steps": [
                {
                    "replay_order": index,
                    "execution_id": execution_id,
                }
                for index, execution_id in enumerate(rollback_order)
            ],
        }

    def _replay_linkage(self, snapshot: RuntimeEvidenceSnapshot) -> dict[str, Any]:
        replay_snapshot = snapshot.export_replay()
        replay_index = self._safe_mapping(replay_snapshot.get("replay_index"))
        if not replay_index:
            return {
                "found": False,
                "replay_id": "",
                "verified": False,
                "lineage_ids": [],
            }
        replay_id = sorted(replay_index)[0]
        replay = self._safe_mapping(replay_index.get(replay_id))
        return {
            "found": True,
            "replay_id": self._safe_text(replay.get("replay_id")),
            "snapshot_id": self._safe_text(replay.get("snapshot_id")),
            "audit_id": self._safe_text(replay.get("audit_id")),
            "bundle_id": self._safe_text(replay.get("bundle_id")),
            "verified": bool(replay.get("verified", False)),
            "lineage_ids": [
                self._safe_text(item)
                for item in replay.get("lineage_ids", [])
                if self._safe_text(item)
            ] if isinstance(replay.get("lineage_ids"), list) else [],
        }

    def _event_replay_order(self, snapshot: RuntimeEvidenceSnapshot) -> list[dict[str, Any]]:
        event_snapshot = snapshot.export_events()
        events = event_snapshot.get("events")
        if not isinstance(events, list):
            events = []
        ordered = sorted(
            [
                event
                for event in events
                if isinstance(event, dict)
            ],
            key=lambda item: (
                self._safe_int(item.get("event_order"), 10**9),
                self._safe_text(item.get("event_key")),
            ),
        )
        return [
            {
                "replay_order": index,
                "event_key": self._safe_text(item.get("event_key")),
                "layer": self._safe_text(item.get("layer")),
                "event_index": item.get("event_index"),
                "phase": self._safe_text(item.get("phase")),
                "status": self._safe_text(item.get("status")),
                "fingerprint": self._safe_text(item.get("fingerprint")),
            }
            for index, item in enumerate(ordered)
        ]

    def _safe_mapping(self, value: Any) -> dict[str, Any]:
        return copy.deepcopy(value) if isinstance(value, dict) else {}

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


def reconstruct_runtime_evidence_replay(source: Any) -> RuntimeEvidenceReplayState:
    return RuntimeEvidenceReplayReconstructor().reconstruct(source)


__all__ = [
    "RuntimeEvidenceReplayReconstructor",
    "RuntimeEvidenceReplayState",
    "reconstruct_runtime_evidence_replay",
]
