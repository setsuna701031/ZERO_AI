from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class RuntimeGovernanceLedgerEntry:
    entry_id: str
    replay_id: str
    closure_id: str
    snapshot_id: str
    sequence: int
    previous_entry_hash: str
    entry_hash: str
    timestamp: str
    immutable: bool
    classification: str
    closure_status: str
    continuation_allowed: bool
    evidence_bundle: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "replay_id": self.replay_id,
            "closure_id": self.closure_id,
            "snapshot_id": self.snapshot_id,
            "sequence": self.sequence,
            "previous_entry_hash": self.previous_entry_hash,
            "entry_hash": self.entry_hash,
            "timestamp": self.timestamp,
            "immutable": self.immutable,
            "classification": self.classification,
            "closure_status": self.closure_status,
            "continuation_allowed": self.continuation_allowed,
            "evidence_bundle": copy.deepcopy(self.evidence_bundle),
        }


class RuntimeGovernanceLedger:
    def __init__(self) -> None:
        self._entries: list[RuntimeGovernanceLedgerEntry] = []

    def append_snapshot(
        self,
        snapshot: Any,
    ) -> RuntimeGovernanceLedgerEntry:
        payload = (
            snapshot.to_dict()
            if hasattr(snapshot, "to_dict")
            else dict(snapshot)
        )

        sequence = len(self._entries) + 1

        previous_hash = (
            self._entries[-1].entry_hash
            if self._entries
            else "genesis"
        )

        timestamp = self._utc_timestamp()

        entry_payload = {
            "replay_id": str(payload.get("replay_id") or ""),
            "closure_id": str(payload.get("closure_id") or ""),
            "snapshot_id": str(payload.get("snapshot_id") or ""),
            "sequence": sequence,
            "previous_entry_hash": previous_hash,
            "timestamp": timestamp,
            "classification": str(payload.get("classification") or ""),
            "closure_status": str(payload.get("closure_status") or ""),
            "continuation_allowed": bool(
                payload.get("continuation_allowed")
            ),
            "evidence_bundle": copy.deepcopy(
                payload.get("evidence_bundle")
                if isinstance(payload.get("evidence_bundle"), dict)
                else {}
            ),
        }

        entry_hash = self._hash_payload(entry_payload)

        entry = RuntimeGovernanceLedgerEntry(
            entry_id=f"ledger::{sequence}",
            replay_id=entry_payload["replay_id"],
            closure_id=entry_payload["closure_id"],
            snapshot_id=entry_payload["snapshot_id"],
            sequence=sequence,
            previous_entry_hash=previous_hash,
            entry_hash=entry_hash,
            timestamp=timestamp,
            immutable=True,
            classification=entry_payload["classification"],
            closure_status=entry_payload["closure_status"],
            continuation_allowed=entry_payload["continuation_allowed"],
            evidence_bundle=entry_payload["evidence_bundle"],
        )

        self._entries.append(entry)

        return self._copy_entry(entry)

    def get_entries(self) -> list[RuntimeGovernanceLedgerEntry]:
        return [
            self._copy_entry(item)
            for item in self._entries
        ]

    def build_audit_chain(self) -> dict[str, Any]:
        entries = self.get_entries()

        return {
            "chain_type": "runtime_governance_ledger",
            "entry_count": len(entries),
            "entries": [
                item.to_dict()
                for item in entries
            ],
            "latest_entry_hash": (
                entries[-1].entry_hash
                if entries
                else ""
            ),
            "immutable": True,
        }

    def verify_chain_integrity(self) -> dict[str, Any]:
        if not self._entries:
            return {
                "verified": True,
                "reason": "empty_chain",
            }

        previous_hash = "genesis"

        for entry in self._entries:
            payload = {
                "replay_id": entry.replay_id,
                "closure_id": entry.closure_id,
                "snapshot_id": entry.snapshot_id,
                "sequence": entry.sequence,
                "previous_entry_hash": entry.previous_entry_hash,
                "timestamp": entry.timestamp,
                "classification": entry.classification,
                "closure_status": entry.closure_status,
                "continuation_allowed": entry.continuation_allowed,
                "evidence_bundle": copy.deepcopy(
                    entry.evidence_bundle
                ),
            }

            expected_hash = self._hash_payload(payload)

            if entry.previous_entry_hash != previous_hash:
                return {
                    "verified": False,
                    "reason": "previous_hash_mismatch",
                    "entry_id": entry.entry_id,
                }

            if entry.entry_hash != expected_hash:
                return {
                    "verified": False,
                    "reason": "entry_hash_mismatch",
                    "entry_id": entry.entry_id,
                }

            previous_hash = entry.entry_hash

        return {
            "verified": True,
            "reason": "ledger_chain_verified",
            "entry_count": len(self._entries),
        }

    def _copy_entry(
        self,
        entry: RuntimeGovernanceLedgerEntry,
    ) -> RuntimeGovernanceLedgerEntry:
        return RuntimeGovernanceLedgerEntry(
            entry_id=entry.entry_id,
            replay_id=entry.replay_id,
            closure_id=entry.closure_id,
            snapshot_id=entry.snapshot_id,
            sequence=entry.sequence,
            previous_entry_hash=entry.previous_entry_hash,
            entry_hash=entry.entry_hash,
            timestamp=entry.timestamp,
            immutable=entry.immutable,
            classification=entry.classification,
            closure_status=entry.closure_status,
            continuation_allowed=entry.continuation_allowed,
            evidence_bundle=copy.deepcopy(
                entry.evidence_bundle
            ),
        )

    def _hash_payload(
        self,
        payload: dict[str, Any],
    ) -> str:
        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

        return hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()

    def _utc_timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()