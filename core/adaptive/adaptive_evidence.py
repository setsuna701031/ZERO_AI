from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Mapping


class AdaptiveEvidenceChain:
    """Append-only adaptive evidence stored inside the existing runtime state."""

    SCHEMA = "zero.adaptive.evidence.v1"

    def append(self, chain: list[dict[str, Any]], *, kind: str, payload: Any) -> dict[str, Any]:
        previous_id = str(chain[-1].get("evidence_id") or "") if chain else ""
        record = {
            "schema": self.SCHEMA,
            "kind": str(kind),
            "payload": copy.deepcopy(payload),
            "previous_evidence_id": previous_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        digest = hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        record["evidence_id"] = f"adaptive-evidence-{digest[:16]}"
        chain.append(record)
        return copy.deepcopy(record)

    def validate(self, chain: list[Mapping[str, Any]]) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        for index, record in enumerate(chain):
            expected = "" if index == 0 else str(chain[index - 1].get("evidence_id") or "")
            if str(record.get("previous_evidence_id") or "") != expected:
                issues.append({"kind": "broken_linkage", "index": index})
        return {"ok": not issues, "evidence_count": len(chain), "issues": issues}


__all__ = ["AdaptiveEvidenceChain"]
