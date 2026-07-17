from __future__ import annotations

"""Read-only state summaries for engineering evidence."""

import copy
import time
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_evidence_policy import EngineeringEvidencePolicy
from core.tasks.engineering_evidence_repository import EngineeringEvidenceRepository


ENGINEERING_EVIDENCE_STATE_SCHEMA = "zero.engineering_evidence_state.v1"
ENGINEERING_EVIDENCE_SUMMARY_SCHEMA = "zero.engineering_evidence_summary.v1"

EVIDENCE_STATES = {"active", "empty", "archived"}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class EngineeringEvidenceState:
    """Evaluate read-only evidence state and aggregate metrics."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        evidence_repository: EngineeringEvidenceRepository | Any | None = None,
        evidence_policy: EngineeringEvidencePolicy | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.evidence_repository = evidence_repository or EngineeringEvidenceRepository(self.repo_root)
        self.evidence_policy = evidence_policy or EngineeringEvidencePolicy()

    def evaluate_evidence_state(self) -> dict[str, Any]:
        evidence = self._list_evidence()
        policy_summary = self.evidence_policy.build_evidence_summary(evidence)
        if not evidence:
            state = "empty"
        elif policy_summary.get("active_count") == 0:
            state = "archived"
        else:
            state = "active"
        return {
            "schema": ENGINEERING_EVIDENCE_STATE_SCHEMA,
            "ok": True,
            "state": state,
            **self.calculate_evidence_metrics(evidence=evidence, policy_summary=policy_summary),
            "policy_summary": policy_summary,
            "updated_at": time.time(),
        }

    def calculate_evidence_metrics(
        self,
        *,
        evidence: list[Mapping[str, Any]] | None = None,
        policy_summary: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        records = [copy.deepcopy(dict(item)) for item in evidence] if evidence is not None else self._list_evidence()
        summary = _as_mapping(policy_summary) or self.evidence_policy.build_evidence_summary(records)
        evidence_type_summary = _as_mapping(summary.get("evidence_type_summary"))
        evidence_types = {
            evidence_type: int(_as_float(type_summary.get("total")))
            for evidence_type, type_summary in evidence_type_summary.items()
            if isinstance(type_summary, Mapping)
        }
        latest_evidence = _as_mapping(summary.get("latest_evidence"))
        return {
            "schema": ENGINEERING_EVIDENCE_STATE_SCHEMA,
            "ok": True,
            "evidence_count": len(records),
            "active_evidence_count": int(_as_float(summary.get("active_count"))),
            "archived_evidence_count": int(_as_float(summary.get("archived_count"))),
            "artifact_evidence_count": len([item for item in records if _clean_text(item.get("artifact_id"))]),
            "goal_evidence_count": len([item for item in records if _clean_text(item.get("goal_id"))]),
            "portfolio_evidence_count": len([item for item in records if _clean_text(item.get("portfolio_id"))]),
            "program_evidence_count": len([item for item in records if _clean_text(item.get("program_id"))]),
            "evidence_types": evidence_types,
            "evidence_type_summary": evidence_type_summary,
            "latest_evidence": latest_evidence,
            "updated_at": time.time(),
        }

    def summarize_evidence(self) -> dict[str, Any]:
        evidence = self._list_evidence()
        state = self.evaluate_evidence_state()
        policy_summary = _as_mapping(state.get("policy_summary"))
        return {
            "schema": ENGINEERING_EVIDENCE_SUMMARY_SCHEMA,
            "ok": True,
            "state": _clean_text(state.get("state"), "empty"),
            "evidence": evidence,
            **self.calculate_evidence_metrics(evidence=evidence, policy_summary=policy_summary),
            "policy_summary": policy_summary,
            "updated_at": time.time(),
        }

    def _list_evidence(self) -> list[dict[str, Any]]:
        ordered = getattr(self.evidence_repository, "_ordered_records", None)
        if callable(ordered):
            return [copy.deepcopy(dict(item)) for item in ordered() if isinstance(item, Mapping)]
        listed = getattr(self.evidence_repository, "list_evidence", None)
        if callable(listed):
            return [copy.deepcopy(dict(item)) for item in listed() if isinstance(item, Mapping)]
        return []


__all__ = [
    "ENGINEERING_EVIDENCE_STATE_SCHEMA",
    "ENGINEERING_EVIDENCE_SUMMARY_SCHEMA",
    "EVIDENCE_STATES",
    "EngineeringEvidenceState",
]
