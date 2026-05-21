from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.runtime.runtime_events import RuntimeEvent
from core.runtime.runtime_replay_session import RuntimeReplayArtifact


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeWorkerDescriptor:
    worker_id: str
    capabilities: tuple[str, ...] = ()
    checkpoint_id: str = ""
    transaction_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "capabilities": list(self.capabilities),
            "checkpoint_id": self.checkpoint_id,
            "transaction_id": self.transaction_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RuntimeExecutionShard:
    shard_id: str
    worker: RuntimeWorkerDescriptor
    operation_ids: tuple[str, ...] = ()
    transaction_id: str = ""
    checkpoint_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "shard_id": self.shard_id,
            "worker": self.worker.to_dict(),
            "operation_ids": list(self.operation_ids),
            "transaction_id": self.transaction_id,
            "checkpoint_id": self.checkpoint_id,
        }


@dataclass(frozen=True)
class RuntimeDistributedEventEnvelope:
    envelope_id: str
    worker_id: str
    shard_id: str
    event: dict[str, Any]
    transaction_id: str
    checkpoint_id: str
    created_at: str = field(default_factory=_utc_now)

    @classmethod
    def from_event(
        cls,
        *,
        worker: RuntimeWorkerDescriptor,
        shard: RuntimeExecutionShard,
        event: RuntimeEvent,
    ) -> "RuntimeDistributedEventEnvelope":
        payload = {
            "worker": worker.to_dict(),
            "shard": shard.to_dict(),
            "event": event.to_dict(),
        }
        return cls(
            envelope_id="runtime-distributed-event-" + _stable_hash(payload)[:16],
            worker_id=worker.worker_id,
            shard_id=shard.shard_id,
            event=event.to_dict(),
            transaction_id=shard.transaction_id or worker.transaction_id,
            checkpoint_id=shard.checkpoint_id or worker.checkpoint_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "worker_id": self.worker_id,
            "shard_id": self.shard_id,
            "event": copy.deepcopy(self.event),
            "transaction_id": self.transaction_id,
            "checkpoint_id": self.checkpoint_id,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RuntimeDistributedReplayArtifact:
    artifact_id: str
    replay_artifact: dict[str, Any]
    workers: tuple[dict[str, Any], ...]
    shards: tuple[dict[str, Any], ...]
    event_envelopes: tuple[dict[str, Any], ...]
    transaction_aware: bool = True
    checkpoint_compatible: bool = True

    @classmethod
    def from_replay(
        cls,
        replay: RuntimeReplayArtifact,
        *,
        workers: tuple[RuntimeWorkerDescriptor, ...],
        shards: tuple[RuntimeExecutionShard, ...],
        envelopes: tuple[RuntimeDistributedEventEnvelope, ...] = (),
    ) -> "RuntimeDistributedReplayArtifact":
        payload = {
            "replay": replay.to_dict(),
            "workers": [worker.to_dict() for worker in workers],
            "shards": [shard.to_dict() for shard in shards],
            "envelopes": [envelope.to_dict() for envelope in envelopes],
        }
        return cls(
            artifact_id="runtime-distributed-replay-" + _stable_hash(payload)[:16],
            replay_artifact=replay.to_dict(),
            workers=tuple(worker.to_dict() for worker in workers),
            shards=tuple(shard.to_dict() for shard in shards),
            event_envelopes=tuple(envelope.to_dict() for envelope in envelopes),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "replay_artifact": copy.deepcopy(self.replay_artifact),
            "workers": [copy.deepcopy(worker) for worker in self.workers],
            "shards": [copy.deepcopy(shard) for shard in self.shards],
            "event_envelopes": [copy.deepcopy(envelope) for envelope in self.event_envelopes],
            "transaction_aware": self.transaction_aware,
            "checkpoint_compatible": self.checkpoint_compatible,
        }


__all__ = [
    "RuntimeDistributedEventEnvelope",
    "RuntimeDistributedReplayArtifact",
    "RuntimeExecutionShard",
    "RuntimeWorkerDescriptor",
]
