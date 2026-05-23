from __future__ import annotations

import copy
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


SNAPSHOT_ACTIVE = "active"
SNAPSHOT_RESTORED = "restored"
SNAPSHOT_ARCHIVED = "archived"

REPLICATION_OK = "replicated"
REPLICATION_FAILED = "failed"

ROLLBACK_ALLOWED = "allowed"
ROLLBACK_BLOCKED = "blocked"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeStateSnapshot:
    snapshot_id: str
    runtime_zone: str
    runtime_state: dict[str, Any]
    status: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "runtime_zone": self.runtime_zone,
            "runtime_state": copy.deepcopy(self.runtime_state),
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RuntimeStateReplicationDecision:
    replication_status: str
    rollback_status: str
    allowed: bool
    reason: str
    snapshot: dict[str, Any]
    replication_log: list[dict[str, Any]]
    created_at: str = field(default_factory=utc_timestamp)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                _stable_fingerprint(self.to_dict(include_fingerprint=False)),
            )

    def to_dict(self, include_fingerprint: bool = True) -> dict[str, Any]:
        payload = {
            "artifact_type": "runtime_state_replication_decision",
            "replication_status": self.replication_status,
            "rollback_status": self.rollback_status,
            "allowed": self.allowed,
            "reason": self.reason,
            "snapshot": copy.deepcopy(self.snapshot),
            "replication_log": copy.deepcopy(self.replication_log),
            "created_at": self.created_at,
        }

        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
            payload["verified"] = self.verify()

        return payload

    def verify(self) -> bool:
        return self.fingerprint == _stable_fingerprint(
            self.to_dict(include_fingerprint=False)
        )


class RuntimeStateReplicationLayer:
    """
    Recoverable runtime state system.

    Maintains runtime state snapshots, replication checkpoints,
    and rollback recovery points.
    """

    def __init__(self) -> None:
        self.snapshots: dict[str, RuntimeStateSnapshot] = {}
        self.replication_log: list[dict[str, Any]] = []

    def create_snapshot(
        self,
        *,
        runtime_zone: str,
        runtime_state: dict[str, Any],
    ) -> RuntimeStateSnapshot:
        snapshot = RuntimeStateSnapshot(
            snapshot_id="snapshot-" + secrets.token_hex(8),
            runtime_zone=str(runtime_zone),
            runtime_state=copy.deepcopy(runtime_state),
            status=SNAPSHOT_ACTIVE,
            created_at=utc_timestamp(),
        )

        self.snapshots[snapshot.snapshot_id] = snapshot

        self.replication_log.append(
            {
                "event": "snapshot_created",
                "snapshot_id": snapshot.snapshot_id,
                "runtime_zone": snapshot.runtime_zone,
            }
        )

        return snapshot

    def replicate_snapshot(
        self,
        *,
        snapshot_id: str,
        target_zone: str,
    ) -> RuntimeStateReplicationDecision:
        snapshot = self.snapshots.get(snapshot_id)

        if snapshot is None:
            return self._decision(
                replication_status=REPLICATION_FAILED,
                rollback_status=ROLLBACK_BLOCKED,
                allowed=False,
                reason="snapshot_not_found",
                snapshot={},
            )

        self.replication_log.append(
            {
                "event": "snapshot_replicated",
                "snapshot_id": snapshot.snapshot_id,
                "target_zone": target_zone,
            }
        )

        return self._decision(
            replication_status=REPLICATION_OK,
            rollback_status=ROLLBACK_ALLOWED,
            allowed=True,
            reason="snapshot_replication_successful",
            snapshot=snapshot.to_dict(),
        )

    def rollback_to_snapshot(
        self,
        *,
        snapshot_id: str,
    ) -> RuntimeStateReplicationDecision:
        snapshot = self.snapshots.get(snapshot_id)

        if snapshot is None:
            return self._decision(
                replication_status=REPLICATION_FAILED,
                rollback_status=ROLLBACK_BLOCKED,
                allowed=False,
                reason="rollback_snapshot_not_found",
                snapshot={},
            )

        restored = RuntimeStateSnapshot(
            snapshot_id=snapshot.snapshot_id,
            runtime_zone=snapshot.runtime_zone,
            runtime_state=snapshot.runtime_state,
            status=SNAPSHOT_RESTORED,
            created_at=snapshot.created_at,
        )

        self.snapshots[snapshot.snapshot_id] = restored

        self.replication_log.append(
            {
                "event": "snapshot_restored",
                "snapshot_id": snapshot.snapshot_id,
            }
        )

        return self._decision(
            replication_status=REPLICATION_OK,
            rollback_status=ROLLBACK_ALLOWED,
            allowed=True,
            reason="runtime_rollback_completed",
            snapshot=restored.to_dict(),
        )

    def _decision(
        self,
        *,
        replication_status: str,
        rollback_status: str,
        allowed: bool,
        reason: str,
        snapshot: dict[str, Any],
    ) -> RuntimeStateReplicationDecision:
        return RuntimeStateReplicationDecision(
            replication_status=replication_status,
            rollback_status=rollback_status,
            allowed=allowed,
            reason=reason,
            snapshot=copy.deepcopy(snapshot),
            replication_log=copy.deepcopy(self.replication_log),
        )


__all__ = [
    "RuntimeStateReplicationLayer",
    "RuntimeStateSnapshot",
    "RuntimeStateReplicationDecision",
    "SNAPSHOT_ACTIVE",
    "SNAPSHOT_RESTORED",
    "SNAPSHOT_ARCHIVED",
    "REPLICATION_OK",
    "REPLICATION_FAILED",
    "ROLLBACK_ALLOWED",
    "ROLLBACK_BLOCKED",
]
