from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class RuntimeGovernanceSnapshot:
    snapshot_id: str
    closure_id: str
    replay_id: str
    snapshot_type: str
    closure_status: str
    classification: str
    continuation_allowed: bool
    review_required: bool
    blocked: bool
    reopen_protection: bool
    timestamp: str
    evidence_bundle: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "closure_id": self.closure_id,
            "replay_id": self.replay_id,
            "snapshot_type": self.snapshot_type,
            "closure_status": self.closure_status,
            "classification": self.classification,
            "continuation_allowed": self.continuation_allowed,
            "review_required": self.review_required,
            "blocked": self.blocked,
            "reopen_protection": self.reopen_protection,
            "timestamp": self.timestamp,
            "evidence_bundle": copy.deepcopy(self.evidence_bundle),
        }


class RuntimeGovernanceSnapshotBuilder:
    def build_snapshot(
        self,
        closure: Any,
        *,
        seal: Any | None = None,
        replay_evidence: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeGovernanceSnapshot:
        closure_payload = (
            closure.to_dict()
            if hasattr(closure, "to_dict")
            else dict(closure)
        )

        seal_payload = (
            seal.to_dict()
            if hasattr(seal, "to_dict")
            else dict(seal)
            if isinstance(seal, dict)
            else {}
        )

        replay_id = str(closure_payload.get("replay_id") or "")
        closure_id = str(closure_payload.get("closure_id") or f"closure::{replay_id}")

        timestamp = self._utc_timestamp()

        evidence_bundle = {
            "closure_snapshot": copy.deepcopy(closure_payload),
            "seal_snapshot": copy.deepcopy(seal_payload),
            "replay_evidence": copy.deepcopy(replay_evidence or {}),
            "governance_evidence": copy.deepcopy(
                closure_payload.get("governance_evidence")
                if isinstance(closure_payload.get("governance_evidence"), dict)
                else {}
            ),
            "metadata": copy.deepcopy(metadata or {}),
            "lineage": {
                "replay_id": replay_id,
                "closure_id": closure_id,
                "seal_id": str(seal_payload.get("seal_id") or ""),
                "recovery_id": str(seal_payload.get("recovery_id") or ""),
                "execution_id": str(seal_payload.get("execution_id") or ""),
            },
            "source": "runtime_governance_snapshot_v1",
        }

        return RuntimeGovernanceSnapshot(
            snapshot_id=f"snapshot::{replay_id or closure_id}",
            closure_id=closure_id,
            replay_id=replay_id,
            snapshot_type="runtime_governance_snapshot",
            closure_status=str(closure_payload.get("closure_status") or ""),
            classification=str(closure_payload.get("classification") or ""),
            continuation_allowed=bool(closure_payload.get("continuation_allowed")),
            review_required=bool(closure_payload.get("review_required")),
            blocked=bool(closure_payload.get("blocked")),
            reopen_protection=bool(closure_payload.get("reopen_protection")),
            timestamp=timestamp,
            evidence_bundle=evidence_bundle,
        )

    def _utc_timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()