from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from core.runtime.runtime_integrity import RuntimeIntegrityReport, stable_fingerprint, verify_integrity
from core.runtime.runtime_events import RuntimeEvent
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


JOURNAL_RESTORE_TRUNCATION_MARKER = "__truncated_for_journal_restore__"
_JOURNAL_RESTORE_MAX_DEPTH = 8
_JOURNAL_RESTORE_MAX_ITEMS = 64
_JOURNAL_RESTORE_ESSENTIAL_KEYS = {
    "abi_version",
    "applied",
    "boundary",
    "checkpoint_id",
    "checkpoint_type",
    "decision_id",
    "event_id",
    "event_type",
    "execution_id",
    "failed",
    "from_state",
    "integrity_hash",
    "mutation_id",
    "mutation_request_id",
    "ok",
    "outcome",
    "phase",
    "reason",
    "record_id",
    "record_type",
    "relative_path",
    "rolled_back",
    "rollback_completed",
    "rollback_required",
    "runtime_version",
    "sequence",
    "session_id",
    "state",
    "status",
    "timestamp",
    "to_state",
    "transaction_id",
    "verified",
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _journal_key_rank(key: Any) -> tuple[int, str]:
    text = str(key)
    return (0 if text in _JOURNAL_RESTORE_ESSENTIAL_KEYS or text.endswith("_id") or text.endswith("_status") else 1, text)


def project_journal_restore_payload(
    value: Any,
    *,
    max_depth: int = _JOURNAL_RESTORE_MAX_DEPTH,
    max_items: int = _JOURNAL_RESTORE_MAX_ITEMS,
) -> Any:
    """Return a deterministic bounded payload for journal restore/reconstruct."""

    seen: set[int] = set()

    def project(item: Any, depth: int) -> Any:
        if item is None or isinstance(item, (str, int, float, bool)):
            return item
        if depth >= max_depth:
            return JOURNAL_RESTORE_TRUNCATION_MARKER
        if isinstance(item, dict):
            item_id = id(item)
            if item_id in seen:
                return JOURNAL_RESTORE_TRUNCATION_MARKER
            seen.add(item_id)
            projected: dict[str, Any] = {}
            keys = sorted(item.keys(), key=_journal_key_rank)
            for key in keys[:max_items]:
                projected[str(key)] = project(item[key], depth + 1)
            if len(keys) > max_items:
                projected[JOURNAL_RESTORE_TRUNCATION_MARKER] = JOURNAL_RESTORE_TRUNCATION_MARKER
            seen.remove(item_id)
            return projected
        if isinstance(item, (list, tuple)):
            item_id = id(item)
            if item_id in seen:
                return JOURNAL_RESTORE_TRUNCATION_MARKER
            seen.add(item_id)
            projected_list = [project(child, depth + 1) for child in list(item)[:max_items]]
            if len(item) > max_items:
                projected_list.append(JOURNAL_RESTORE_TRUNCATION_MARKER)
            seen.remove(item_id)
            return projected_list
        return str(item)

    return project(value, 0)


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
        object.__setattr__(
            self,
            "payload",
            project_journal_restore_payload(self.payload if isinstance(self.payload, dict) else {}),
        )
        object.__setattr__(
            self,
            "metadata",
            project_journal_restore_payload(self.metadata if isinstance(self.metadata, dict) else {}),
        )
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
            "payload": project_journal_restore_payload(self.payload),
            "metadata": project_journal_restore_payload(self.metadata),
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
                project_journal_restore_payload(record.payload)
                for record in records
                if record.record_type == "runtime_event"
                and record.payload.get("event_type") == "RuntimeStateTransitionEvent"
            ],
            "transaction_boundaries": [
                project_journal_restore_payload(record.payload)
                for record in records
                if record.record_type.startswith("transaction_")
            ],
            "memory_snapshots": [
                project_journal_restore_payload(record.payload)
                for record in records
                if record.record_type == "runtime_memory_snapshot"
            ],
            "capability_state": [
                project_journal_restore_payload(record.payload)
                for record in records
                if record.record_type == "runtime_capability_graph"
            ],
            "intent_state": [
                project_journal_restore_payload(record.payload)
                for record in records
                if record.record_type == "runtime_intent_evaluation"
            ],
            "scheduler_state": [
                project_journal_restore_payload(record.payload)
                for record in records
                if record.record_type == "runtime_scheduler_state"
            ],
            "distributed_state": [
                project_journal_restore_payload(record.payload)
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


__all__ = [
    "JOURNAL_RESTORE_TRUNCATION_MARKER",
    "RuntimeJournal",
    "RuntimeJournalEntry",
    "RuntimeWALRecord",
    "project_journal_restore_payload",
]
