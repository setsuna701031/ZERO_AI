"""Runtime state snapshots for governed mutation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import hashlib
from typing import Any


MAX_INLINE_SNAPSHOT_BYTES = 1024 * 1024

IGNORED_PATH_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "workspace",
}


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
        metadata: dict[str, Any] = {}

        if _is_ignored_path(path):
            return RuntimeStateSnapshotRecord(
                target_path=str(path),
                content_hash=hash_bytes(b""),
                timestamp=timestamp,
                exists=exists,
                content=None,
                metadata={
                    "size": 0,
                    "snapshot_skipped": True,
                    "skip_reason": "ignored_runtime_path",
                },
            )

        if not exists or not path.is_file():
            return RuntimeStateSnapshotRecord(
                target_path=str(path),
                content_hash=hash_bytes(b""),
                timestamp=timestamp,
                exists=exists,
                content=None,
                metadata={"size": 0},
            )

        size = path.stat().st_size
        metadata["size"] = size

        if size > MAX_INLINE_SNAPSHOT_BYTES:
            return RuntimeStateSnapshotRecord(
                target_path=str(path),
                content_hash=_hash_file_streaming(path),
                timestamp=timestamp,
                exists=True,
                content=None,
                metadata={
                    **metadata,
                    "snapshot_skipped": True,
                    "skip_reason": "file_too_large_for_inline_snapshot",
                    "max_inline_snapshot_bytes": MAX_INLINE_SNAPSHOT_BYTES,
                },
            )

        content = path.read_bytes()
        return RuntimeStateSnapshotRecord(
            target_path=str(path),
            content_hash=hash_bytes(content),
            timestamp=timestamp,
            exists=True,
            content=content,
            metadata=metadata,
        )


def _is_ignored_path(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts.intersection(IGNORED_PATH_PARTS))


def _hash_file_streaming(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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