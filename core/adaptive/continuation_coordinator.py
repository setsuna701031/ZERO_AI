from __future__ import annotations

"""Coordinator for adaptive continuation work-item creation.

ContinuationCoordinator owns the continuation-work-item construction that used
to live in EngineeringGoalLoop.  It may call the injected goal repository to
save the continuation record, but it does not execute runtime work, decide
adaptive actions, write evidence, or touch memory.
"""

import copy
import time
from pathlib import Path
from typing import Any, Mapping

from core.adaptive.continuation_runtime import ContinuationRuntime
from core.goals.goal_lineage_contract import attach_goal_lineage, extract_goal_lineage


CONTINUATION_COORDINATOR_SCHEMA = "zero.continuation_coordinator.v1"
ENGINEERING_CONTINUATION_WORK_ITEM_SCHEMA = "zero.engineering_goal_loop.continuation_work_item.v2"


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _transport(value: Any) -> Any:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _transport(to_dict())
    if isinstance(value, Mapping):
        return {str(key): _transport(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_transport(item) for item in value]
    if isinstance(value, tuple):
        return [_transport(item) for item in value]
    return copy.deepcopy(value)


class ContinuationCoordinator:
    """Create continuation work items without owning loop decisions."""

    def __init__(self, *, repo_root: str | Path | None = None, repository: Any) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else None
        self.repository = repository

    def create_work_item(
        self,
        *,
        runtime: ContinuationRuntime,
        cycle: Mapping[str, Any],
        goal_id: str = "",
        cycle_index: int | None = None,
        continuation_plan: Mapping[str, Any] | None = None,
        runner_result: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], ContinuationRuntime]:
        """Create a continuation work item and return the updated runtime."""

        if runtime.limit_reached:
            raise RuntimeError("continuation_limit_reached")
        cycle_record = _mapping(cycle)
        plan = _mapping(continuation_plan) or _mapping(cycle_record.get("continuation_plan"))
        next_request = _mapping(plan.get("next_runtime_request"))
        payload = _mapping(next_request.get("payload"))
        work_item_template = _mapping(plan.get("work_item_template"))
        source_goal_id = _text(
            goal_id
            or cycle_record.get("goal_id")
            or plan.get("goal_id")
            or next_request.get("goal_id")
            or runtime.current_goal_id,
            runtime.current_goal_id,
        )
        resolved_cycle_index = int(cycle_index if cycle_index is not None else cycle_record.get("cycle_index") or 0)
        session_id = _text(cycle_record.get("session_id") or cycle_record.get("runtime_session_id"))
        continuation_goal_id = self._continuation_goal_id(source_goal_id, resolved_cycle_index)
        parent_lineage = extract_goal_lineage(cycle_record)
        lineage = extract_goal_lineage(
            {
                **parent_lineage,
                "goal_id": continuation_goal_id,
                "source_goal_id": source_goal_id,
                "branch_type": "continuation",
                "branch_id": continuation_goal_id,
                "continuation_id": continuation_goal_id,
            },
            require_complete=True,
        )
        evidence_refs = [
            _text(item.get("evidence_id"))
            for item in (plan.get("evidence_chain") or [])
            if isinstance(item, Mapping) and _text(item.get("evidence_id"))
        ]
        attestation = _mapping(cycle_record.get("goal_completion_authority_result"))
        if not attestation:
            transported_attestation = _transport(cycle_record.get("goal_completion_attestation"))
            attestation = _mapping(transported_attestation)
        authority_state = (
            "completion_authority_accepted"
            if bool(attestation.get("accepted")) and bool(attestation.get("completed"))
            else "completion_authority_not_granted"
        )
        summary = _text(payload.get("goal") or plan.get("reason"), f"Continue {source_goal_id}")
        payload["goal_id"] = continuation_goal_id
        payload["task_id"] = continuation_goal_id
        payload["package_id"] = continuation_goal_id
        payload["source_goal_id"] = source_goal_id
        payload["continuation_goal_id"] = continuation_goal_id
        payload["continuation_task_id"] = continuation_goal_id
        payload["continuation_source_goal_id"] = source_goal_id
        payload["continuation_cycle_index"] = resolved_cycle_index
        payload["continuation_requested"] = True
        payload = attach_goal_lineage(payload, lineage)
        if session_id:
            payload["session_id"] = session_id
        payload["continuation_objective"] = _text(work_item_template.get("objective"), summary)
        payload["continuation_acceptance"] = _mapping(work_item_template.get("acceptance"))
        payload["adaptive_evidence_chain"] = copy.deepcopy(plan.get("evidence_chain") or [])

        record = self.repository.save_goal(
            attach_goal_lineage({
                "schema": ENGINEERING_CONTINUATION_WORK_ITEM_SCHEMA,
                "goal_id": continuation_goal_id,
                "summary": summary,
                "status": "pending",
                "priority": 0.0,
                "payload": payload,
                "metadata": {
                    "source": "continuation_coordinator",
                    "source_goal_id": source_goal_id,
                    "source_cycle_index": resolved_cycle_index,
                    **({"session_id": session_id} if session_id else {}),
                    "continuation_plan": plan,
                    "work_item_template": work_item_template,
                    "adaptive_evidence_chain": copy.deepcopy(plan.get("evidence_chain") or []),
                    "runner_adaptive_decision": _transport(_mapping(_mapping(runner_result).get("adaptive_decision"))),
                    "adaptive_planning_record": _transport(_mapping(
                        _mapping(_mapping(runner_result).get("adaptive_decision")).get("adaptive_planning_record")
                    )),
                    "continuation_coordinator_schema": CONTINUATION_COORDINATOR_SCHEMA,
                },
            }, lineage)
        )
        work_item = attach_goal_lineage({
            "schema": ENGINEERING_CONTINUATION_WORK_ITEM_SCHEMA,
            "goal_id": record["goal_id"],
            "task_id": record["goal_id"],
            "continuation_goal_id": record["goal_id"],
            "continuation_task_id": record["goal_id"],
            "source_goal_id": source_goal_id,
            "cycle_index": resolved_cycle_index,
            **({"session_id": session_id} if session_id else {}),
            "evidence_ref": evidence_refs[0] if evidence_refs else "",
            "evidence_refs": list(dict.fromkeys(evidence_refs)),
            "decision_evidence_id": "",
            "authority_state": authority_state,
            "record": record,
            "continuation_coordinator": {
                "schema": CONTINUATION_COORDINATOR_SCHEMA,
                "created_work_item": True,
                "execution_path": {
                    "coordinator_only": True,
                    "executes_tasks": False,
                    "decides_adaptive_action": False,
                    "writes_evidence": False,
                    "mutates_runtime": False,
                    "mutates_memory": False,
                },
            },
            "created_at": time.time(),
        }, lineage)
        return work_item, runtime.record_work_item(work_item)

    def _continuation_goal_id(self, source_goal_id: str, cycle_index: int) -> str:
        base = f"{_text(source_goal_id, 'goal')}__continuation_{int(cycle_index) + 1}"
        return base


__all__ = [
    "CONTINUATION_COORDINATOR_SCHEMA",
    "ENGINEERING_CONTINUATION_WORK_ITEM_SCHEMA",
    "ContinuationCoordinator",
]
