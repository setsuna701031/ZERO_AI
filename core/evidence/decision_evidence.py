from __future__ import annotations

"""Durable decision evidence persistence with no execution capability."""

import copy
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping

from core.evidence.decision_evidence_models import DecisionEvidenceRecord


DECISION_EVIDENCE_STORE_SCHEMA = "zero.decision_evidence.store.v1"


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


class DecisionEvidenceRepository:
    """Persist and query decision judgments only."""

    def __init__(self, repo_root: str | Path, *, storage_path: str | Path | None = None) -> None:
        self.repo_root = Path(repo_root)
        self.storage_path = (
            Path(storage_path)
            if storage_path is not None
            else self.repo_root / "runtime" / "evidence" / "decision_evidence.json"
        )
        if not self.storage_path.is_absolute():
            self.storage_path = self.repo_root / self.storage_path

    def save(self, record: Mapping[str, Any]) -> dict[str, Any]:
        normalized = copy.deepcopy(dict(record))
        decision_id = _text(normalized.get("decision_id"))
        if not decision_id:
            raise ValueError("decision_evidence_requires_decision_id")
        records = self.list_records()
        by_id = {_text(item.get("decision_id")): item for item in records}
        by_id[decision_id] = normalized
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": DECISION_EVIDENCE_STORE_SCHEMA,
            "records": sorted(by_id.values(), key=lambda item: (float(item.get("created_at") or 0), _text(item.get("decision_id")))),
            "updated_at": time.time(),
        }
        self.storage_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return copy.deepcopy(normalized)

    def list_records(self) -> list[dict[str, Any]]:
        if not self.storage_path.is_file():
            return []
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        records = payload.get("records") if isinstance(payload, Mapping) else []
        return [copy.deepcopy(dict(item)) for item in records if isinstance(item, Mapping)] if isinstance(records, list) else []

    def find_by_task_id(self, task_id: str) -> list[dict[str, Any]]:
        target = _text(task_id)
        return [record for record in self.list_records() if _text(record.get("task_id")) == target]

    def find_by_goal_id(self, goal_id: str) -> list[dict[str, Any]]:
        target = _text(goal_id)
        return [record for record in self.list_records() if _text(record.get("goal_id")) == target]


__all__ = [
    "DECISION_EVIDENCE_STORE_SCHEMA",
    "DecisionEvidenceRepository",
    "build_decision_evidence",
]
