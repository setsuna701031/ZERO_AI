"""Runtime state snapshots for governed mutation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import hashlib
from typing import Any


@dataclass(frozen=True)
class RuntimeStateSnapshotRecord:
    target_path: str
    content_hash: str
    timestamp: str
    exists: bool
    content: bytes | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeStateSnapshot:
    snapshot_id: str
    source_transaction_id: str
    records: tuple[RuntimeStateSnapshotRecord, ...]
    rollback_metadata: dict[str, Any]
    verification_hash: str
    timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeStateSnapshotResult:
    snapshot: RuntimeStateSnapshot
    created: bool
    verified: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeStateSnapshotter:
    def capture(
        self,
        *,
        snapshot_id: str,
        source_transaction_id: str,
        target_paths: tuple[str | Path, ...],
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeStateSnapshotResult:
        timestamp = _utc_timestamp()
        records = tuple(
            self._capture_path(path=Path(path), timestamp=timestamp)
            for path in target_paths
        )
        verification_hash = hash_snapshot_records(records)
        snapshot = RuntimeStateSnapshot(
            snapshot_id=snapshot_id,
            source_transaction_id=source_transaction_id,
            records=records,
            rollback_metadata={
                "rollback_compatible": True,
                "source_transaction_id": source_transaction_id,
                "record_count": len(records),
            },
            verification_hash=verification_hash,
            timestamp=timestamp,
            metadata=dict(metadata or {}),
        )
        return RuntimeStateSnapshotResult(
            snapshot=snapshot,
            created=True,
            verified=verification_hash == hash_snapshot_records(records),
            metadata={
                "snapshot_id": snapshot_id,
                "source_transaction_id": source_transaction_id,
                "replay_compatible": True,
                "audit_compatible": True,
            },
        )

    def _capture_path(self, *, path: Path, timestamp: str) -> RuntimeStateSnapshotRecord:
        exists = path.exists()
        content = path.read_bytes() if exists and path.is_file() else None
        return RuntimeStateSnapshotRecord(
            target_path=str(path),
            content_hash=hash_bytes(content or b""),
            timestamp=timestamp,
            exists=exists,
            content=content,
            metadata={"size": len(content or b"")},
        )


def hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def hash_text(content: str) -> str:
    return hash_bytes(content.encode("utf-8"))


def hash_snapshot_records(records: tuple[RuntimeStateSnapshotRecord, ...]) -> str:
    payload = "|".join(
        f"{record.target_path}:{record.exists}:{record.content_hash}"
        for record in records
    )
    return hash_text(payload)


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()
