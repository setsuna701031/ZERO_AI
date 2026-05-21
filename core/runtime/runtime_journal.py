from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from core.runtime.runtime_integrity import RuntimeIntegrityReport, stable_fingerprint, verify_integrity
from core.runtime.runtime_events import RuntimeEvent
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeWALRecord:
    sequence: int
    record_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)
    record_id: str = ""
    runtime_version: str = RUNTIME_KERNEL_VERSION
    abi_version: str = RUNTIME_ABI_VERSION
    integrity_hash: str = ""

    def __post_init__(self) -> None:
        record_type = str(self.record_type or "").strip()
        if not record_type:
            raise ValueError("runtime_wal_record_type_required")
        object.__setattr__(self, "record_type", record_type)
        object.__setattr__(self, "payload", copy.deepcopy(dict(self.payload or {})))
        object.__setattr__(self, "metadata", copy.deepcopy(dict(self.metadata or {})))
        if not self.record_id:
            seed = {
                "sequence": self.sequence,
                "record_type": record_type,
                "payload": self.payload,
                "metadata": self.metadata,
            }
            object.__setattr__(self, "record_id", "runtime-wal-" + _stable_hash(seed)[:16])
        if not self.runtime_version:
            object.__setattr__(self, "runtime_version", RUNTIME_KERNEL_VERSION)
        if not self.abi_version:
            object.__setattr__(self, "abi_version", RUNTIME_ABI_VERSION)
        if not self.integrity_hash:
            object.__setattr__(
                self,
                "integrity_hash",
                stable_fingerprint(self.to_dict(include_integrity=False)),
            )

    def to_dict(self, include_integrity: bool = True) -> dict[str, Any]:
        payload = {
            "record_id": self.record_id,
            "runtime_version": self.runtime_version,
            "abi_version": self.abi_version,
            "sequence": self.sequence,
            "record_type": self.record_type,
            "timestamp": self.timestamp,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
        }
        if include_integrity:
            payload["integrity_hash"] = self.integrity_hash
        return payload

    def verify_integrity(self) -> RuntimeIntegrityReport:
        return verify_integrity(self.to_dict(), artifact_type="runtime_wal_record")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeWALRecord":
        return cls(
            sequence=int(payload.get("sequence") or 0),
            record_type=str(payload.get("record_type") or ""),
            payload=dict(payload.get("payload") or {}),
            metadata=dict(payload.get("metadata") or {}),
            timestamp=str(payload.get("timestamp") or utc_timestamp()),
            record_id=str(payload.get("record_id") or ""),
            runtime_version=str(payload.get("runtime_version") or RUNTIME_KERNEL_VERSION),
            abi_version=str(payload.get("abi_version") or RUNTIME_ABI_VERSION),
            integrity_hash=str(payload.get("integrity_hash") or ""),
        )


@dataclass(frozen=True)
class RuntimeJournalEntry:
    entry_id: str
    sequence: int
    record: RuntimeWALRecord

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "sequence": self.sequence,
            "record": self.record.to_dict(),
        }


class RuntimeJournal:
    """Append-only runtime journal with WAL-compatible reconstruction."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._records: list[RuntimeWALRecord] = []
        self._sequence = 0
        if self.path and self.path.exists():
            self.restore_from_journal(self.path)

    @property
    def records(self) -> tuple[RuntimeWALRecord, ...]:
        return tuple(self._records)

    def append(
        self,
        record_type: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeJournalEntry:
        self._sequence += 1
        record = RuntimeWALRecord(
            sequence=self._sequence,
            record_type=record_type,
            payload=payload or {},
            metadata=metadata or {},
        )
        self._records.append(record)
        self._persist_record(record)
        return RuntimeJournalEntry(
            entry_id=f"runtime-journal-entry-{record.sequence}",
            sequence=record.sequence,
            record=record,
        )

    def append_event(
        self,
        event: RuntimeEvent,
        *,
        phase: str = "before_apply",
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeJournalEntry:
        return self.append(
            "runtime_event",
            payload=event.to_dict(),
            metadata={"phase": phase, **dict(metadata or {})},
        )

    def append_transaction_boundary(
        self,
        boundary: str,
        transaction_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeJournalEntry:
        return self.append(
            f"transaction_{boundary}",
            payload={"transaction_id": str(transaction_id or ""), "boundary": boundary},
            metadata=metadata,
        )

    def replay_records(self) -> list[RuntimeWALRecord]:
        return list(sorted(self._records, key=lambda item: item.sequence))

    def reconstruct(self) -> dict[str, Any]:
        records = self.replay_records()
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_journal",
            "record_count": len(records),
            "last_sequence": records[-1].sequence if records else 0,
            "integrity": self.verify_integrity().to_dict(),
            "state_transitions": [
                record.payload
                for record in records
                if record.record_type == "runtime_event"
                and record.payload.get("event_type") == "RuntimeStateTransitionEvent"
            ],
            "transaction_boundaries": [
                record.payload
                for record in records
                if record.record_type.startswith("transaction_")
            ],
            "memory_snapshots": [
                record.payload
                for record in records
                if record.record_type == "runtime_memory_snapshot"
            ],
            "capability_state": [
                record.payload
                for record in records
                if record.record_type == "runtime_capability_graph"
            ],
            "intent_state": [
                record.payload
                for record in records
                if record.record_type == "runtime_intent_evaluation"
            ],
            "scheduler_state": [
                record.payload
                for record in records
                if record.record_type == "runtime_scheduler_state"
            ],
            "distributed_state": [
                record.payload
                for record in records
                if record.record_type == "runtime_distributed_replay"
            ],
            "records": [record.to_dict() for record in records],
        }

    def restore_from_journal(self, path: str | Path | None = None) -> dict[str, Any]:
        journal_path = Path(path) if path is not None else self.path
        if journal_path is None:
            raise ValueError("runtime_journal_path_required")
        records: list[RuntimeWALRecord] = []
        if journal_path.exists():
            for line in journal_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                records.append(RuntimeWALRecord.from_dict(json.loads(line)))
        records.sort(key=lambda item: item.sequence)
        self._records = records
        self._sequence = records[-1].sequence if records else 0
        return self.reconstruct()

    def verify_integrity(self) -> RuntimeIntegrityReport:
        failures = [record.verify_integrity().to_dict() for record in self._records if not record.verify_integrity().verified]
        if failures:
            return RuntimeIntegrityReport(
                artifact_type="runtime_journal",
                verified=False,
                reason="runtime_wal_integrity_failure",
                metadata={"failures": failures},
            )
        return RuntimeIntegrityReport(
            artifact_type="runtime_journal",
            verified=True,
            actual_fingerprint=_stable_hash([record.to_dict() for record in self._records]),
            reason="runtime_wal_integrity_verified",
        )

    @classmethod
    def from_records(cls, records: Iterable[RuntimeWALRecord]) -> "RuntimeJournal":
        journal = cls()
        journal._records = list(sorted(records, key=lambda item: item.sequence))
        journal._sequence = journal._records[-1].sequence if journal._records else 0
        return journal

    def _persist_record(self, record: RuntimeWALRecord) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), sort_keys=True, default=str) + "\n")


__all__ = ["RuntimeJournal", "RuntimeJournalEntry", "RuntimeWALRecord"]
