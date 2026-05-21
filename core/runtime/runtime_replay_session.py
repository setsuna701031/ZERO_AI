from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_seal import attach_runtime_seal
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeSessionSnapshot:
    snapshot_id: str
    state_progression: tuple[dict[str, Any], ...]
    transaction_boundaries: tuple[dict[str, Any], ...]
    mutation_decisions: tuple[dict[str, Any], ...]
    verification_results: tuple[dict[str, Any], ...]
    rollback_paths: tuple[dict[str, Any], ...]
    recovery_flows: tuple[dict[str, Any], ...]
    evidence_bundles: tuple[dict[str, Any], ...]
    runtime_events: tuple[dict[str, Any], ...]
    memory_snapshots: tuple[dict[str, Any], ...] = ()
    capability_state: tuple[dict[str, Any], ...] = ()
    intent_state: tuple[dict[str, Any], ...] = ()
    scheduler_state: tuple[dict[str, Any], ...] = ()
    distributed_state: tuple[dict[str, Any], ...] = ()
    wal_reconstruction: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_session_snapshot",
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at,
            "state_progression": [copy.deepcopy(item) for item in self.state_progression],
            "transaction_boundaries": [copy.deepcopy(item) for item in self.transaction_boundaries],
            "mutation_decisions": [copy.deepcopy(item) for item in self.mutation_decisions],
            "verification_results": [copy.deepcopy(item) for item in self.verification_results],
            "rollback_paths": [copy.deepcopy(item) for item in self.rollback_paths],
            "recovery_flows": [copy.deepcopy(item) for item in self.recovery_flows],
            "evidence_bundles": [copy.deepcopy(item) for item in self.evidence_bundles],
            "runtime_events": [copy.deepcopy(item) for item in self.runtime_events],
            "memory_snapshots": [copy.deepcopy(item) for item in self.memory_snapshots],
            "capability_state": [copy.deepcopy(item) for item in self.capability_state],
            "intent_state": [copy.deepcopy(item) for item in self.intent_state],
            "scheduler_state": [copy.deepcopy(item) for item in self.scheduler_state],
            "distributed_state": [copy.deepcopy(item) for item in self.distributed_state],
            "wal_reconstruction": copy.deepcopy(self.wal_reconstruction),
        }


@dataclass(frozen=True)
class RuntimeReplayArtifact:
    replay_id: str
    session_snapshot: RuntimeSessionSnapshot
    journal_records: tuple[dict[str, Any], ...]
    deterministic: bool = True
    replayable: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_replay_artifact",
            "replay_id": self.replay_id,
            "deterministic": self.deterministic,
            "replayable": self.replayable,
            "session_snapshot": self.session_snapshot.to_dict(),
            "journal_records": [copy.deepcopy(item) for item in self.journal_records],
        }
        return attach_runtime_seal(payload, artifact_type="runtime_replay_artifact")


class RuntimeReplaySession:
    def __init__(self, journal: RuntimeJournal, *, replay_id: str = "") -> None:
        self.journal = journal
        self.replay_id = replay_id or "runtime-replay-" + _stable_hash(journal.reconstruct())[:16]

    def reconstruct(self) -> RuntimeReplayArtifact:
        reconstruction = self.journal.reconstruct()
        records = reconstruction["records"]
        events = [
            record["payload"]
            for record in records
            if record["record_type"] == "runtime_event"
        ]
        event_payloads = [event.get("payload", {}) for event in events]
        snapshot_payload = {
            "events": events,
            "records": records,
            "reconstruction": reconstruction,
        }
        snapshot = RuntimeSessionSnapshot(
            snapshot_id="runtime-session-snapshot-" + _stable_hash(snapshot_payload)[:16],
            state_progression=[
                event
                for event in events
                if event.get("event_type") == "RuntimeStateTransitionEvent"
            ],
            transaction_boundaries=tuple(reconstruction["transaction_boundaries"]),
            mutation_decisions=tuple(
                event
                for event in events
                if event.get("event_type") in {"MutationAppliedEvent"}
            ),
            verification_results=tuple(
                event
                for event in events
                if event.get("event_type") == "VerificationCompletedEvent"
            ),
            rollback_paths=tuple(
                event
                for event in events
                if event.get("event_type") in {"RollbackTriggeredEvent", "TransactionRolledBackEvent"}
            ),
            recovery_flows=tuple(
                event
                for event in events
                if event.get("event_type") in {"RecoveryStartedEvent", "RecoveryCompletedEvent"}
            ),
            evidence_bundles=tuple(
                event
                for event in events
                if event.get("event_type") == "EvidenceAttachedEvent"
            ),
            runtime_events=tuple(events),
            memory_snapshots=tuple(reconstruction.get("memory_snapshots") or ()),
            capability_state=tuple(reconstruction.get("capability_state") or ()),
            intent_state=tuple(reconstruction.get("intent_state") or ()),
            scheduler_state=tuple(reconstruction.get("scheduler_state") or ()),
            distributed_state=tuple(reconstruction.get("distributed_state") or ()),
            wal_reconstruction=reconstruction,
        )
        return RuntimeReplayArtifact(
            replay_id=self.replay_id,
            session_snapshot=snapshot,
            journal_records=tuple(records),
        )


__all__ = [
    "RuntimeReplayArtifact",
    "RuntimeReplaySession",
    "RuntimeSessionSnapshot",
]
