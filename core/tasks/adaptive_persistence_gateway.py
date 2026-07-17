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

from core.runtime.runtime_result_projection import detach_internal_result

from core.evidence.decision_evidence import DecisionEvidenceRepository, build_decision_evidence
from core.evidence.evidence_authority import EvidenceAuthority
from core.evidence.evidence_repository import EvidenceRepository
from core.tasks.adaptive_planning_foundation import ADAPTIVE_PLANNING_RECORD_SCHEMA
from core.goals.goal_lineage_contract import extract_goal_lineage, lineage_scope_matches


ADAPTIVE_PERSISTENCE_GATEWAY_SCHEMA = "zero.adaptive_persistence_gateway.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return detach_internal_result(value) if isinstance(value, Mapping) else {}


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
        lineage = extract_goal_lineage(cycle, require_complete=True, reject_conflicts=True)

        self.persist_goal_adaptive_metadata(cycle, record)
        decision_evidence = self.register_decision_evidence(cycle)
        cycle["decision_evidence"] = detach_internal_result(decision_evidence)
        cycle["evidence_chain"] = self.evidence_chain_summary(
            _clean_text(cycle.get("goal_id")),
            goal_lineage=lineage,
        )
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
            "previous_step": detach_internal_result(record.get("previous_step")),
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
            "adaptive_replan_contract": _as_mapping(cycle.get("adaptive_replan_contract")),
            "persistence_gateway_schema": ADAPTIVE_PERSISTENCE_GATEWAY_SCHEMA,
        })
        return record

    def persist_goal_adaptive_metadata(self, cycle: Mapping[str, Any], record: Mapping[str, Any]) -> None:
        update_goal = getattr(self.repository, "update_goal", None)
        if callable(update_goal):
            goal_id = _clean_text(cycle.get("goal_id"))
            load_goal = getattr(self.repository, "load_goal", None)
            if not callable(load_goal):
                raise TypeError("adaptive_persistence_requires_goal_repository_load")
            goal = load_goal(goal_id)
            if not isinstance(goal, Mapping):
                raise ValueError("adaptive_persistence_goal_record_required")
            persisted_lineage = extract_goal_lineage(
                goal, require_complete=True, reject_conflicts=True
            )
            cycle_lineage = extract_goal_lineage(
                cycle, require_complete=True, reject_conflicts=True
            )
            if not lineage_scope_matches(persisted_lineage, cycle_lineage):
                raise ValueError("adaptive_persistence_goal_lineage_conflict")
            metadata = _as_mapping(_as_mapping(goal).get("metadata"))
            history = [
                detach_internal_result(item)
                for item in metadata.get("adaptive_planning_history", [])
                if isinstance(item, Mapping)
            ] if isinstance(metadata.get("adaptive_planning_history"), list) else []
            history.append(detach_internal_result(record))
            update_goal(
                goal_id,
                {
                    "metadata": {
                        "goal_lineage": detach_internal_result(extract_goal_lineage(cycle)),
                        "adaptive_planning_record": detach_internal_result(record),
                        "adaptive_planning_history": history,
                    }
                },
            )

    def register_decision_evidence(self, cycle: Mapping[str, Any]) -> dict[str, Any]:
        extract_goal_lineage(cycle, require_complete=True, reject_conflicts=True)
        decision_evidence = build_decision_evidence(
            cycle=cycle,
            continuation_work_item=_as_mapping(cycle.get("continuation_work_item")),
            replan_record=_as_mapping(cycle.get("replan_record")),
        )
        register_decision_evidence = getattr(self.evidence_authority, "register_decision_evidence", None)
        if callable(register_decision_evidence):
            return detach_internal_result(register_decision_evidence(decision_evidence))
        raise TypeError("adaptive_persistence_requires_evidence_authority")

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
            continuation_work_item["evidence_ref"] = decision_id
            continuation_refs = [
                _clean_text(item)
                for item in continuation_work_item.get("evidence_refs", [])
                if _clean_text(item)
            ] if isinstance(continuation_work_item.get("evidence_refs"), list) else []
            if decision_id not in continuation_refs:
                continuation_refs.append(decision_id)
            continuation_work_item["evidence_refs"] = continuation_refs
            cycle["continuation_work_item"] = continuation_work_item
        if cycle.get("replan_record"):
            replan_record = _as_mapping(cycle.get("replan_record"))
            replan_request = _as_mapping(replan_record.get("replan_request"))
            if replan_request.get("request_id") and not replan_record.get("replan_request_id"):
                replan_record["replan_request_id"] = _clean_text(replan_request.get("request_id"))
            replan_record["decision_evidence_id"] = decision_id
            replan_record["evidence_ref"] = decision_id
            evidence_refs = [
                _clean_text(item)
                for item in replan_record.get("evidence_refs", [])
                if _clean_text(item)
            ] if isinstance(replan_record.get("evidence_refs"), list) else []
            if decision_id not in evidence_refs:
                evidence_refs.append(decision_id)
            replan_record["evidence_refs"] = evidence_refs
            cycle["replan_record"] = replan_record

    def evidence_chain_summary(
        self,
        goal_id: str,
        *,
        goal_lineage: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        get_goal_chain = getattr(self.evidence_authority, "get_goal_chain", None)
        if not callable(get_goal_chain):
            build_chain = getattr(self.evidence_repository, "build_chain", None)
            if not callable(build_chain):
                return {}
            chain_factory = build_chain
        else:
            chain_factory = get_goal_chain
        try:
            lineage = extract_goal_lineage(goal_lineage)
            chain = chain_factory(
                _clean_text(goal_id),
                session_id=lineage.get("session_id") or None,
                goal_lineage_id=lineage.get("goal_lineage_id") or None,
                root_goal_id=lineage.get("root_goal_id") or None,
            )
        except Exception:
            return {}
        to_dict = getattr(chain, "to_dict", None)
        return detach_internal_result(to_dict()) if callable(to_dict) else {}


__all__ = ["ADAPTIVE_PERSISTENCE_GATEWAY_SCHEMA", "AdaptivePersistenceGateway"]
