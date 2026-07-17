from __future__ import annotations

"""Single evidence authority for ZERO evidence aggregation.

EvidenceAuthority is the only write-facing aggregation boundary for evidence.
It does not execute runtime actions, validate evidence by itself, mutate goal
state, or write memory.  It delegates append-only persistence to
EvidenceRepository and exposes read-only EvidenceChain summaries for Goal and
Adaptive layers.
"""

import copy
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.evidence.evidence_chain import EvidenceChain
from core.evidence.evidence_record import EvidenceRecord
from core.evidence.evidence_repository import EvidenceRepository
from core.goals.goal_contract import clean_optional_text, clean_required_text


EVIDENCE_AUTHORITY_SCHEMA = "zero.evidence_authority.v1"
DECISION_EVIDENCE_SOURCE = "decision_evidence"


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


class EvidenceAuthority:
    """Aggregate evidence through one repository-backed authority boundary."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        repository: EvidenceRepository | Any | None = None,
        evidence_repository: EvidenceRepository | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.repository = repository or evidence_repository or EvidenceRepository(self.repo_root)

    def register_evidence(self, record: EvidenceRecord | Mapping[str, Any]) -> EvidenceRecord:
        """Persist a generic evidence record.

        This is a persistence handoff only.  The authority does not decide goal
        completion, validate runtime output, or mutate GoalRepository.
        """

        evidence = record if isinstance(record, EvidenceRecord) else EvidenceRecord.from_mapping(record)
        add_record = getattr(self.repository, "add_record", None)
        if not callable(add_record):
            raise TypeError("evidence_authority_requires_repository_add_record")
        return add_record(evidence)

    def register_decision_evidence(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Project a decision-evidence record into the unified evidence chain."""

        normalized = copy.deepcopy(dict(record))
        evidence = self.decision_evidence_to_record(normalized)
        stored = self.register_evidence(evidence)
        normalized["evidence_id"] = stored.evidence_id
        normalized["evidence_source"] = DECISION_EVIDENCE_SOURCE
        normalized["evidence_authority_schema"] = EVIDENCE_AUTHORITY_SCHEMA
        return normalized

    def get_goal_chain(
        self,
        goal_id: str,
        *,
        session_id: str | None = None,
        goal_lineage_id: str | None = None,
        root_goal_id: str | None = None,
    ) -> EvidenceChain:
        target = clean_required_text(goal_id, "goal_id")
        build_chain = getattr(self.repository, "build_chain", None)
        if callable(build_chain) and session_id is None and goal_lineage_id is None and root_goal_id is None:
            return build_chain(target)
        records = self._records_for_goal(
            target,
            session_id=session_id,
            goal_lineage_id=goal_lineage_id,
            root_goal_id=root_goal_id,
        )
        return EvidenceChain.from_records(target, records)

    def get_subgoal_chain(self, goal_id: str, subgoal_id: str) -> EvidenceChain:
        target_goal = clean_required_text(goal_id, "goal_id")
        target_subgoal = clean_required_text(subgoal_id, "subgoal_id")
        build_chain = getattr(self.repository, "build_chain", None)
        if callable(build_chain):
            return build_chain(target_goal, subgoal_id=target_subgoal)
        records = self._records_for_goal(target_goal)
        return EvidenceChain.from_records(target_goal, records, subgoal_id=target_subgoal)

    def get_decision_chain(self, goal_id: str, *, task_id: str | None = None, session_id: str | None = None) -> EvidenceChain:
        target_goal = clean_required_text(goal_id, "goal_id")
        target_task = clean_optional_text(task_id)
        records = [record for record in self._records_for_goal(target_goal, session_id=session_id) if record.source == DECISION_EVIDENCE_SOURCE]
        if target_task is not None:
            records = [record for record in records if record.subgoal_id == target_task]
        return EvidenceChain.from_records(target_goal, records, subgoal_id=target_task)

    def build_goal_evidence_summary(self, goal_id: str, *, session_id: str | None = None) -> dict[str, Any]:
        chain = self.get_goal_chain(goal_id, session_id=session_id)
        decision_chain = self.get_decision_chain(goal_id, session_id=session_id)
        summary = chain.to_dict()
        summary.update(
            {
                "schema": EVIDENCE_AUTHORITY_SCHEMA,
                "goal_id": chain.goal_id,
                "session_id": str(session_id or ""),
                "decision_evidence_ids": copy.deepcopy(decision_chain.evidence_ids),
                "validated_decision_evidence_ids": copy.deepcopy(decision_chain.validated_evidence_ids),
                "decision_validation_summary": copy.deepcopy(dict(decision_chain.validation_summary)),
                "has_decision_evidence": bool(decision_chain.evidence_ids),
            }
        )
        return summary

    def list_records(self) -> list[EvidenceRecord]:
        list_records = getattr(self.repository, "list_records", None)
        if callable(list_records):
            return list_records()
        return []

    def _records_for_goal(
        self,
        goal_id: str,
        *,
        session_id: str | None = None,
        goal_lineage_id: str | None = None,
        root_goal_id: str | None = None,
    ) -> list[EvidenceRecord]:
        list_by_goal = getattr(self.repository, "list_by_goal", None)
        if callable(list_by_goal):
            try:
                return list_by_goal(
                    goal_id,
                    session_id=session_id,
                    goal_lineage_id=goal_lineage_id,
                    root_goal_id=root_goal_id,
                )
            except TypeError:
                records = list_by_goal(goal_id)
                if session_id is None:
                    return records
                return [
                    record for record in records
                    if _text(_mapping(record.metadata).get("session_id")) == str(session_id)
                ]
        return [
            record for record in self.list_records()
            if record.goal_id == goal_id
            and (
                session_id is None
                or _text(_mapping(record.metadata).get("session_id")) == str(session_id)
            )
        ]

    @staticmethod
    def decision_evidence_to_record(record: Mapping[str, Any]) -> EvidenceRecord:
        normalized = _mapping(record)
        decision_id = _text(normalized.get("decision_id"))
        if not decision_id:
            raise ValueError("decision_evidence_requires_decision_id")
        goal_id = _text(normalized.get("goal_id"), "decision_goal_unavailable")
        task_id = _text(normalized.get("task_id"))
        decision = _text(normalized.get("decision"), "unavailable")
        outcome = _text(normalized.get("outcome_class"), "unavailable")
        reason = _text(normalized.get("decision_reason"), "decision_reason_unavailable")
        summary = f"decision={decision}; outcome={outcome}; reason={reason}"
        return EvidenceRecord.from_mapping(
            {
                "evidence_id": decision_id,
                "goal_id": goal_id,
                "subgoal_id": task_id,
                "source": DECISION_EVIDENCE_SOURCE,
                "summary": summary,
                "timestamp": float(normalized.get("created_at") or time.time()),
                "validation_state": "pending",
                "metadata": {
                    "decision_id": decision_id,
                    "task_id": task_id,
                    "session_id": _text(normalized.get("session_id")),
                    "runtime_session_id": _text(normalized.get("runtime_session_id")),
                    "root_goal_id": _text(normalized.get("root_goal_id")),
                    "source_goal_id": _text(normalized.get("source_goal_id")),
                    "goal_lineage_id": _text(normalized.get("goal_lineage_id")),
                    "branch_type": _text(normalized.get("branch_type")),
                    "branch_id": _text(normalized.get("branch_id")),
                    "goal_lineage": _mapping(normalized.get("goal_lineage")),
                    "source_stage": _text(normalized.get("source_stage")),
                    "next_action": _text(normalized.get("next_action")),
                    "links": _mapping(normalized.get("links")),
                    "evidence_refs": _list(normalized.get("evidence_refs")),
                    "observed_event": _mapping(normalized.get("observed_event")),
                    "confidence": copy.deepcopy(normalized.get("confidence")),
                    "confidence_unavailable_reason": _text(normalized.get("confidence_unavailable_reason")),
                },
            }
        )


__all__ = [
    "DECISION_EVIDENCE_SOURCE",
    "EVIDENCE_AUTHORITY_SCHEMA",
    "EvidenceAuthority",
]
