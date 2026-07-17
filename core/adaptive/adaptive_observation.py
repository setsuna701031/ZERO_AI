from __future__ import annotations

"""Passive observations for Adaptive Loop v2.

AdaptiveObservation summarizes one completed engineering runtime cycle.  It is
read-only and does not execute runtime work, decide adaptive actions, persist
records, mutate repositories, or write memory.
"""

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Mapping


ADAPTIVE_OBSERVATION_SCHEMA = "zero.adaptive_loop.observation.v2"


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


@dataclass(frozen=True)
class AdaptiveObservation:
    goal_id: str
    cycle_index: int
    runtime_state: str = ""
    runtime_ok: bool = False
    adaptive_decision: str = ""
    stop_reason: str = ""
    evidence_count: int = 0
    validated_evidence_count: int = 0
    remaining_task_count: int = 0
    completed_task_count: int = 0
    failed_task_count: int = 0
    blocked_task_count: int = 0
    root_cause_available: bool = False
    source_cycle: Mapping[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        object.__setattr__(self, "goal_id", _text(self.goal_id, "goal"))
        object.__setattr__(self, "cycle_index", max(0, int(self.cycle_index or 0)))
        object.__setattr__(self, "runtime_state", _text(self.runtime_state))
        object.__setattr__(self, "runtime_ok", bool(self.runtime_ok))
        object.__setattr__(self, "adaptive_decision", _text(self.adaptive_decision))
        object.__setattr__(self, "stop_reason", _text(self.stop_reason))
        object.__setattr__(self, "evidence_count", max(0, int(self.evidence_count or 0)))
        object.__setattr__(self, "validated_evidence_count", max(0, int(self.validated_evidence_count or 0)))
        object.__setattr__(self, "remaining_task_count", max(0, int(self.remaining_task_count or 0)))
        object.__setattr__(self, "completed_task_count", max(0, int(self.completed_task_count or 0)))
        object.__setattr__(self, "failed_task_count", max(0, int(self.failed_task_count or 0)))
        object.__setattr__(self, "blocked_task_count", max(0, int(self.blocked_task_count or 0)))
        object.__setattr__(self, "root_cause_available", bool(self.root_cause_available))
        object.__setattr__(self, "source_cycle", _mapping(self.source_cycle))
        object.__setattr__(self, "created_at", float(self.created_at or time.time()))

    @classmethod
    def from_cycle(cls, cycle: Mapping[str, Any]) -> "AdaptiveObservation":
        record = _mapping(cycle)
        runtime_contract = _mapping(record.get("engineering_runtime_contract"))
        runtime_result = _mapping(runtime_contract.get("runtime_result") or record.get("runtime_result"))
        adaptive = _mapping(runtime_contract.get("adaptive_decision") or record.get("adaptive_decision_record"))
        progress = _mapping(adaptive.get("progress"))
        evidence_chain = record.get("evidence_chain") or adaptive.get("evidence_chain") or []
        evidence_summary = _mapping(evidence_chain) if isinstance(evidence_chain, Mapping) else {}
        evidence_items = _list(evidence_chain)
        root_cause = _mapping(record.get("root_cause") or adaptive.get("root_cause") or runtime_contract.get("runtime_root_cause"))
        return cls(
            goal_id=_text(record.get("goal_id") or runtime_contract.get("goal_id")),
            cycle_index=int(record.get("cycle_index") or 0),
            runtime_state=_text(record.get("runtime_state") or runtime_result.get("state")),
            runtime_ok=bool(record.get("ok") or runtime_contract.get("ok") or runtime_result.get("ok")),
            adaptive_decision=_text(record.get("adaptive_decision") or adaptive.get("decision")),
            stop_reason=_text(runtime_result.get("stop_reason") or runtime_contract.get("stop_reason")),
            evidence_count=int(evidence_summary.get("validated_count") or evidence_summary.get("evidence_count") or len(evidence_items)),
            validated_evidence_count=int(evidence_summary.get("validated_count") or _count(evidence_summary.get("validated_evidence_ids")) or 0),
            remaining_task_count=_count(progress.get("remaining_tasks")),
            completed_task_count=_count(progress.get("completed_tasks")),
            failed_task_count=_count(progress.get("failed_tasks")),
            blocked_task_count=_count(progress.get("blocked_tasks")),
            root_cause_available=bool(root_cause),
            source_cycle=record,
            created_at=float(record.get("updated_at") or time.time()),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AdaptiveObservation":
        record = _mapping(value)
        return cls(
            goal_id=record.get("goal_id"),
            cycle_index=int(record.get("cycle_index") or 0),
            runtime_state=record.get("runtime_state"),
            runtime_ok=bool(record.get("runtime_ok")),
            adaptive_decision=record.get("adaptive_decision"),
            stop_reason=record.get("stop_reason"),
            evidence_count=int(record.get("evidence_count") or 0),
            validated_evidence_count=int(record.get("validated_evidence_count") or 0),
            remaining_task_count=int(record.get("remaining_task_count") or 0),
            completed_task_count=int(record.get("completed_task_count") or 0),
            failed_task_count=int(record.get("failed_task_count") or 0),
            blocked_task_count=int(record.get("blocked_task_count") or 0),
            root_cause_available=bool(record.get("root_cause_available")),
            source_cycle=_mapping(record.get("source_cycle")),
            created_at=float(record.get("created_at") or time.time()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ADAPTIVE_OBSERVATION_SCHEMA,
            "goal_id": self.goal_id,
            "cycle_index": self.cycle_index,
            "runtime_state": self.runtime_state,
            "runtime_ok": self.runtime_ok,
            "adaptive_decision": self.adaptive_decision,
            "stop_reason": self.stop_reason,
            "evidence_count": self.evidence_count,
            "validated_evidence_count": self.validated_evidence_count,
            "remaining_task_count": self.remaining_task_count,
            "completed_task_count": self.completed_task_count,
            "failed_task_count": self.failed_task_count,
            "blocked_task_count": self.blocked_task_count,
            "root_cause_available": self.root_cause_available,
            "created_at": self.created_at,
            "execution_path": {
                "observation_only": True,
                "executes_tasks": False,
                "persists_records": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


def build_adaptive_observation_from_cycle(cycle: Mapping[str, Any]) -> dict[str, Any]:
    return AdaptiveObservation.from_cycle(cycle).to_dict()


__all__ = ["ADAPTIVE_OBSERVATION_SCHEMA", "AdaptiveObservation", "build_adaptive_observation_from_cycle"]
