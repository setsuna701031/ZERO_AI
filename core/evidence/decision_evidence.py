from __future__ import annotations

"""Decision evidence projection onto the unified evidence authority.

Decision evidence is no longer an independent persistence authority.  The
DecisionEvidenceRepository name is retained as a compatibility projection/view,
but writes are routed through EvidenceAuthority into EvidenceRepository.
"""

import copy
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping

from core.evidence.decision_evidence_models import DecisionEvidenceRecord
from core.evidence.evidence_authority import (
    DECISION_EVIDENCE_SOURCE,
    EvidenceAuthority,
)
from core.evidence.evidence_chain import EvidenceChain
from core.evidence.evidence_record import EvidenceRecord
from core.evidence.evidence_repository import EvidenceRepository


DECISION_EVIDENCE_STORE_SCHEMA = "zero.decision_evidence.projection.v2"
DECISION_EVIDENCE_BRIDGE_SOURCE = DECISION_EVIDENCE_SOURCE


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def build_decision_evidence(
    *,
    cycle: Mapping[str, Any],
    continuation_work_item: Mapping[str, Any] | None = None,
    replan_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cycle_record = _mapping(cycle)
    adaptive = _mapping(cycle_record.get("adaptive_decision_record"))
    planning = _mapping(cycle_record.get("adaptive_planning_record"))
    runner = _mapping(cycle_record.get("runner_result"))
    runtime = _mapping(runner.get("runtime_result"))
    iterations = _list(runtime.get("iterations"))
    latest_iteration = _mapping(iterations[-1]) if iterations else {}
    continuation = _mapping(latest_iteration.get("continuation_result"))
    latest_result = _mapping(continuation.get("latest_result"))
    task_id = _text(
        latest_result.get("task_id")
        or latest_result.get("task_name")
        or adaptive.get("task_id")
        or planning.get("previous_step")
    )
    goal_id = _text(cycle_record.get("goal_id") or adaptive.get("goal_id"))
    cycle_index = int(cycle_record.get("cycle_index") or 0)
    decision = _text(adaptive.get("decision"), "unavailable")
    outcome_class = _text(planning.get("outcome_class") or adaptive.get("outcome_class"), "unavailable")
    next_action = _text(planning.get("next_action") or adaptive.get("next_action"), "unavailable")
    reason = _text(
        planning.get("decision_reason")
        or cycle_record.get("decision_reason")
        or adaptive.get("decision_reason")
        or adaptive.get("reason"),
        "decision_reason_unavailable",
    )
    evidence_refs = []
    for item in _list(adaptive.get("evidence_chain")):
        if isinstance(item, Mapping):
            evidence_refs.append(_text(item.get("evidence_id")) or copy.deepcopy(dict(item)))
        elif item not in (None, ""):
            evidence_refs.append(copy.deepcopy(item))
    links = {
        "continuation_goal_id": _text(_mapping(continuation_work_item).get("goal_id")),
        "replan_goal_id": _text(_mapping(replan_record).get("goal_id")),
        "cycle_index": cycle_index,
    }
    seed = json.dumps(
        {
            "goal_id": goal_id,
            "task_id": task_id,
            "cycle_index": cycle_index,
            "decision": decision,
            "outcome_class": outcome_class,
        },
        sort_keys=True,
    )
    decision_id = f"decision_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:20]}"
    confidence = adaptive.get("confidence")
    if confidence in (None, ""):
        confidence = None
    return DecisionEvidenceRecord(
        decision_id=decision_id,
        goal_id=goal_id,
        task_id=task_id,
        source_stage="engineering_goal_loop",
        observed_event={
            "runtime_state": _text(runtime.get("state")),
            "runtime_stop_reason": _text(runtime.get("stop_reason")),
            "goal_state": _text(_mapping(continuation.get("goal_lifecycle")).get("goal_state")),
            "failed_tasks": _list(_mapping(continuation.get("goal_lifecycle")).get("failed_tasks")),
        },
        outcome_class=outcome_class,
        decision=decision,
        decision_reason=reason,
        confidence=copy.deepcopy(confidence),
        confidence_unavailable_reason="confidence_not_present_in_adaptive_decision",
        next_action=next_action,
        evidence_refs=evidence_refs,
        created_at=time.time(),
        links=links,
    ).to_dict()


def decision_evidence_to_evidence_record(record: Mapping[str, Any]) -> EvidenceRecord:
    return EvidenceAuthority.decision_evidence_to_record(record)


class DecisionEvidenceRepository:
    """Compatibility projection backed by EvidenceAuthority.

    The class keeps the old query API so existing callers do not break, but it
    does not maintain a separate decision-evidence store.  save() registers a
    decision evidence projection with EvidenceAuthority, which persists through
    EvidenceRepository.
    """

    def __init__(
        self,
        repo_root: str | Path,
        *,
        storage_path: str | Path | None = None,
        evidence_repository: EvidenceRepository | Any | None = None,
        evidence_authority: EvidenceAuthority | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.evidence_repository = evidence_repository or EvidenceRepository(self.repo_root)
        self.evidence_authority = evidence_authority or EvidenceAuthority(
            self.repo_root,
            evidence_repository=self.evidence_repository,
        )

    def save(self, record: Mapping[str, Any]) -> dict[str, Any]:
        normalized = copy.deepcopy(dict(record))
        decision_id = _text(normalized.get("decision_id"))
        if not decision_id:
            raise ValueError("decision_evidence_requires_decision_id")
        register = getattr(self.evidence_authority, "register_decision_evidence", None)
        if not callable(register):
            raise TypeError("decision_evidence_projection_requires_evidence_authority")
        return copy.deepcopy(register(normalized))

    def list_records(self) -> list[dict[str, Any]]:
        records = self._decision_evidence_records()
        return [self._record_to_decision_dict(record) for record in records]

    def find_by_task_id(self, task_id: str) -> list[dict[str, Any]]:
        target = _text(task_id)
        return [record for record in self.list_records() if _text(record.get("task_id")) == target]

    def find_by_goal_id(self, goal_id: str) -> list[dict[str, Any]]:
        target = _text(goal_id)
        return [record for record in self.list_records() if _text(record.get("goal_id")) == target]

    def evidence_chain_for_goal(self, goal_id: str) -> EvidenceChain:
        get_decision_chain = getattr(self.evidence_authority, "get_decision_chain", None)
        if callable(get_decision_chain):
            return get_decision_chain(goal_id)
        return EvidenceChain.from_records(goal_id, self._decision_evidence_records())

    def _decision_evidence_records(self) -> list[EvidenceRecord]:
        list_records = getattr(self.evidence_repository, "list_records", None)
        if not callable(list_records):
            return []
        return [record for record in list_records() if getattr(record, "source", "") == DECISION_EVIDENCE_SOURCE]

    @staticmethod
    def _record_to_decision_dict(record: EvidenceRecord) -> dict[str, Any]:
        metadata = _mapping(getattr(record, "metadata", {}))
        decision_id = _text(metadata.get("decision_id"), getattr(record, "evidence_id", ""))
        return {
            "schema": DECISION_EVIDENCE_STORE_SCHEMA,
            "decision_id": decision_id,
            "evidence_id": getattr(record, "evidence_id", decision_id),
            "goal_id": getattr(record, "goal_id", ""),
            "task_id": metadata.get("task_id") or getattr(record, "subgoal_id", ""),
            "source_stage": metadata.get("source_stage", ""),
            "decision": "projected",
            "decision_reason": getattr(record, "summary", ""),
            "next_action": metadata.get("next_action", ""),
            "evidence_refs": _list(metadata.get("evidence_refs")),
            "created_at": getattr(record, "timestamp", 0.0),
            "links": _mapping(metadata.get("links")),
            "projection_only": True,
        }


__all__ = [
    "DECISION_EVIDENCE_BRIDGE_SOURCE",
    "DECISION_EVIDENCE_STORE_SCHEMA",
    "DecisionEvidenceRepository",
    "build_decision_evidence",
    "decision_evidence_to_evidence_record",
]
