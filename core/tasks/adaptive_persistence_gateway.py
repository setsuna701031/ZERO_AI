from __future__ import annotations

"""Persistence boundary for engineering adaptive loop records.

AdaptivePersistenceGateway owns the persistence side effects that used to live
inside EngineeringGoalLoop: adaptive planning metadata updates, decision evidence
registration, and continuation/replan metadata linking.

It does not execute runtime work, decide adaptive actions, mutate runtime
internals, or write memory.  EngineeringGoalLoop remains the loop/orchestration
owner and delegates persistence through this gateway.
"""

import copy
from pathlib import Path
from typing import Any, Mapping

from core.evidence.decision_evidence import DecisionEvidenceRepository, build_decision_evidence
from core.evidence.evidence_authority import EvidenceAuthority
from core.evidence.evidence_repository import EvidenceRepository
from core.tasks.adaptive_planning_foundation import ADAPTIVE_PLANNING_RECORD_SCHEMA


ADAPTIVE_PERSISTENCE_GATEWAY_SCHEMA = "zero.adaptive_persistence_gateway.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


class AdaptivePersistenceGateway:
    """Persist adaptive loop artifacts without owning loop decisions."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        repository: Any,
        decision_evidence_repository: DecisionEvidenceRepository | Any | None = None,
        evidence_repository: EvidenceRepository | Any | None = None,
        evidence_authority: EvidenceAuthority | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.repository = repository
        self.evidence_repository = evidence_repository or EvidenceRepository(self.repo_root)
        self.evidence_authority = evidence_authority or EvidenceAuthority(
            self.repo_root,
            evidence_repository=self.evidence_repository,
        )
        self.decision_evidence_repository = decision_evidence_repository or DecisionEvidenceRepository(
            self.repo_root,
            evidence_repository=self.evidence_repository,
            evidence_authority=self.evidence_authority,
        )

    def persist_cycle(
        self,
        cycle: dict[str, Any],
        *,
        replan_count: int,
        continuation_count: int,
        max_replans: int,
        max_continuations: int,
    ) -> dict[str, Any]:
        """Persist one adaptive cycle and return the updated cycle mapping."""

        record = self.build_adaptive_planning_record(
            cycle,
            replan_count=replan_count,
            continuation_count=continuation_count,
            max_replans=max_replans,
            max_continuations=max_continuations,
        )
        cycle["adaptive_planning_record"] = record
        cycle["outcome_class"] = record["outcome_class"]
        cycle["decision_reason"] = record["decision_reason"]
        cycle["replan_count"] = int(replan_count)
        cycle["continuation_count"] = int(continuation_count)

        self.persist_goal_adaptive_metadata(cycle, record)
        decision_evidence = self.register_decision_evidence(cycle)
        cycle["decision_evidence"] = copy.deepcopy(decision_evidence)
        cycle["evidence_chain"] = self.evidence_chain_summary(_clean_text(cycle.get("goal_id")))
        self.link_decision_evidence(cycle, decision_evidence)
        cycle["adaptive_persistence_gateway"] = {
            "schema": ADAPTIVE_PERSISTENCE_GATEWAY_SCHEMA,
            "persisted_adaptive_planning_record": True,
            "registered_decision_evidence": bool(_clean_text(decision_evidence.get("decision_id"))),
            "updated_goal_metadata": callable(getattr(self.repository, "update_goal", None)),
            "execution_path": {
                "persistence_only": True,
                "executes_tasks": False,
                "decides_adaptive_action": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }
        return cycle

    def build_adaptive_planning_record(
        self,
        cycle: Mapping[str, Any],
        *,
        replan_count: int,
        continuation_count: int,
        max_replans: int,
        max_continuations: int,
    ) -> dict[str, Any]:
        record = _as_mapping(cycle.get("adaptive_planning_record"))
        adaptive = _as_mapping(cycle.get("adaptive_decision_record"))
        record.update({
            "schema": _clean_text(record.get("schema"), ADAPTIVE_PLANNING_RECORD_SCHEMA),
            "previous_goal": _clean_text(record.get("previous_goal"), _clean_text(cycle.get("goal_id"))),
            "previous_step": copy.deepcopy(record.get("previous_step")),
            "outcome_class": _clean_text(record.get("outcome_class"), _clean_text(adaptive.get("outcome_class"))),
            "decision_reason": _clean_text(
                record.get("decision_reason"),
                _clean_text(cycle.get("decision_reason") or adaptive.get("decision_reason") or adaptive.get("reason")),
            ),
            "next_action": _clean_text(record.get("next_action"), _clean_text(adaptive.get("next_action"), "stop")),
            "replan_count": int(replan_count),
            "continuation_count": int(continuation_count),
            "max_replans": int(max_replans),
            "max_continuations": int(max_continuations),
            "adaptive_replan_contract": copy.deepcopy(_as_mapping(cycle.get("adaptive_replan_contract"))),
            "persistence_gateway_schema": ADAPTIVE_PERSISTENCE_GATEWAY_SCHEMA,
        })
        return record

    def persist_goal_adaptive_metadata(self, cycle: Mapping[str, Any], record: Mapping[str, Any]) -> None:
        update_goal = getattr(self.repository, "update_goal", None)
        if callable(update_goal):
            goal_id = _clean_text(cycle.get("goal_id"))
            load_goal = getattr(self.repository, "load_goal", None)
            goal = load_goal(goal_id) if callable(load_goal) else {}
            metadata = _as_mapping(_as_mapping(goal).get("metadata"))
            history = [
                copy.deepcopy(dict(item))
                for item in metadata.get("adaptive_planning_history", [])
                if isinstance(item, Mapping)
            ] if isinstance(metadata.get("adaptive_planning_history"), list) else []
            history.append(copy.deepcopy(dict(record)))
            update_goal(
                goal_id,
                {
                    "metadata": {
                        "adaptive_planning_record": copy.deepcopy(dict(record)),
                        "adaptive_planning_history": history,
                    }
                },
            )

    def register_decision_evidence(self, cycle: Mapping[str, Any]) -> dict[str, Any]:
        decision_evidence = build_decision_evidence(
            cycle=cycle,
            continuation_work_item=_as_mapping(cycle.get("continuation_work_item")),
            replan_record=_as_mapping(cycle.get("replan_record")),
        )
        register_decision_evidence = getattr(self.evidence_authority, "register_decision_evidence", None)
        if callable(register_decision_evidence):
            return copy.deepcopy(dict(register_decision_evidence(decision_evidence)))
        save_evidence = getattr(self.decision_evidence_repository, "save", None)
        if callable(save_evidence):
            return copy.deepcopy(dict(save_evidence(decision_evidence)))
        return copy.deepcopy(dict(decision_evidence))

    def link_decision_evidence(self, cycle: dict[str, Any], decision_evidence: Mapping[str, Any]) -> None:
        update_goal = getattr(self.repository, "update_goal", None)
        decision_id = _clean_text(decision_evidence.get("decision_id"))
        if not callable(update_goal) or not decision_id:
            return

        goal_id = _clean_text(cycle.get("goal_id"))
        goal = self.repository.load_goal(goal_id) or {}
        metadata = _as_mapping(goal.get("metadata"))
        decision_ids = [
            _clean_text(item)
            for item in metadata.get("decision_evidence_ids", [])
            if _clean_text(item)
        ] if isinstance(metadata.get("decision_evidence_ids"), list) else []
        if decision_id not in decision_ids:
            decision_ids.append(decision_id)
        update_goal(goal_id, {"metadata": {"decision_evidence_ids": decision_ids}})

        continuation_goal_id = _clean_text(_as_mapping(cycle.get("continuation_work_item")).get("goal_id"))
        if continuation_goal_id:
            update_goal(continuation_goal_id, {"metadata": {"decision_evidence_id": decision_id}})
            continuation_work_item = _as_mapping(cycle.get("continuation_work_item"))
            continuation_work_item["decision_evidence_id"] = decision_id
            cycle["continuation_work_item"] = continuation_work_item
        if cycle.get("replan_record"):
            replan_record = _as_mapping(cycle.get("replan_record"))
            replan_record["decision_evidence_id"] = decision_id
            cycle["replan_record"] = replan_record

    def evidence_chain_summary(self, goal_id: str) -> dict[str, Any]:
        get_goal_chain = getattr(self.evidence_authority, "get_goal_chain", None)
        if not callable(get_goal_chain):
            build_chain = getattr(self.evidence_repository, "build_chain", None)
            if not callable(build_chain):
                return {}
            chain_factory = build_chain
        else:
            chain_factory = get_goal_chain
        try:
            chain = chain_factory(_clean_text(goal_id))
        except Exception:
            return {}
        to_dict = getattr(chain, "to_dict", None)
        return copy.deepcopy(to_dict()) if callable(to_dict) else {}


__all__ = ["ADAPTIVE_PERSISTENCE_GATEWAY_SCHEMA", "AdaptivePersistenceGateway"]
