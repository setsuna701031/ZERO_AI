from __future__ import annotations

"""Collect pending evidence without validating or mutating goals."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.evidence.evidence_contract import EvidenceContract
from core.evidence.evidence_record import EvidenceRecord


class EvidenceCollector:
    def collect(
        self,
        contract: EvidenceContract,
        *,
        source: str,
        summary: Any,
        timestamp: str | None = None,
    ) -> EvidenceRecord:
        if not isinstance(contract, EvidenceContract):
            raise TypeError("evidence_collector_requires_evidence_contract")
        recorded_at = timestamp or datetime.now(timezone.utc).isoformat()
        seed = json.dumps(
            {
                "plan_id": contract.plan_id,
                "goal_id": contract.goal_id,
                "subgoal_id": contract.subgoal_id,
                "source": source,
                "summary": summary,
                "timestamp": recorded_at,
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        return EvidenceRecord(
            evidence_id=f"evidence:{hashlib.sha256(seed).hexdigest()[:20]}",
            goal_id=contract.goal_id,
            subgoal_id=contract.subgoal_id,
            source=source,
            summary=summary,
            timestamp=recorded_at,
            validation_state="pending",
        )


__all__ = ["EvidenceCollector"]
