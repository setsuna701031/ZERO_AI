from __future__ import annotations

"""Read-only observability summaries for engineering evidence."""

import copy
import time
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_evidence_repository import EngineeringEvidenceRepository
from core.tasks.engineering_evidence_state import EngineeringEvidenceState


ENGINEERING_EVIDENCE_OBSERVABILITY_SCHEMA = "zero.engineering_evidence_observability.v1"
ENGINEERING_EVIDENCE_TREE_SUMMARY_SCHEMA = "zero.engineering_evidence_observability.tree.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


class EngineeringEvidenceObservability:
    """Build read-only evidence rollups from evidence summaries."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        evidence_repository: EngineeringEvidenceRepository | Any | None = None,
        evidence_state: EngineeringEvidenceState | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.evidence_repository = evidence_repository or EngineeringEvidenceRepository(self.repo_root)
        self.evidence_state = evidence_state or EngineeringEvidenceState(
            self.repo_root,
            evidence_repository=self.evidence_repository,
        )

    def calculate_rollup_metrics(self) -> dict[str, Any]:
        summary = self.evidence_state.summarize_evidence()
        return {
            "schema": ENGINEERING_EVIDENCE_OBSERVABILITY_SCHEMA,
            "ok": bool(summary.get("ok")),
            "state": _clean_text(summary.get("state"), "empty"),
            "evidence_count": int(summary.get("evidence_count") or 0),
            "active_evidence_count": int(summary.get("active_evidence_count") or 0),
            "archived_evidence_count": int(summary.get("archived_evidence_count") or 0),
            "artifact_evidence_count": int(summary.get("artifact_evidence_count") or 0),
            "goal_evidence_count": int(summary.get("goal_evidence_count") or 0),
            "portfolio_evidence_count": int(summary.get("portfolio_evidence_count") or 0),
            "program_evidence_count": int(summary.get("program_evidence_count") or 0),
            "evidence_type_summary": _as_mapping(summary.get("evidence_type_summary")),
            "latest_evidence": _as_mapping(summary.get("latest_evidence")),
            "updated_at": time.time(),
        }

    def build_evidence_tree_summary(self) -> dict[str, Any]:
        summary = self.evidence_state.summarize_evidence()
        evidence = summary.get("evidence") if isinstance(summary.get("evidence"), list) else []
        tree = {
            "programs": self._group_by(evidence, "program_id"),
            "portfolios": self._group_by(evidence, "portfolio_id"),
            "goals": self._group_by(evidence, "goal_id"),
            "artifacts": self._group_by(evidence, "artifact_id"),
        }
        return {
            "schema": ENGINEERING_EVIDENCE_TREE_SUMMARY_SCHEMA,
            "ok": bool(summary.get("ok")),
            "state": _clean_text(summary.get("state"), "empty"),
            "tree": tree,
            **self.calculate_rollup_metrics(),
            "updated_at": time.time(),
        }

    def _group_by(self, evidence: list[Any], field: str) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for item in evidence:
            if not isinstance(item, Mapping):
                continue
            key = _clean_text(item.get(field))
            if not key:
                continue
            groups.setdefault(key, []).append(copy.deepcopy(dict(item)))
        id_field = field
        return [
            {
                id_field: key,
                "evidence_count": len(records),
                "evidence": records,
            }
            for key, records in sorted(groups.items(), key=lambda pair: pair[0])
        ]


__all__ = [
    "ENGINEERING_EVIDENCE_OBSERVABILITY_SCHEMA",
    "ENGINEERING_EVIDENCE_TREE_SUMMARY_SCHEMA",
    "EngineeringEvidenceObservability",
]
