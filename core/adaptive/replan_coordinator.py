from __future__ import annotations

"""Coordinator for adaptive replan record creation."""

import copy
import time
from pathlib import Path
from typing import Any, Mapping

from core.adaptive.replan_runtime import ReplanRuntime
from core.goals.goal_lineage_contract import attach_goal_lineage, extract_goal_lineage


REPLAN_COORDINATOR_SCHEMA = "zero.replan_coordinator.v1"
ENGINEERING_REPLAN_RECORD_SCHEMA = "zero.engineering_goal_loop.replan_record.v2"


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return copy.deepcopy(list(value)) if isinstance(value, list) else []


class ReplanCoordinator:
    """Create replan records without owning loop or planner decisions."""

    def __init__(self, *, repo_root: str | Path | None = None) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else None

    def create_replan_record(
        self,
        *,
        runtime: ReplanRuntime,
        cycle: Mapping[str, Any],
        goal_id: str = "",
        cycle_index: int | None = None,
        replan_request: Mapping[str, Any] | None = None,
        runner_result: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], ReplanRuntime]:
        if runtime.limit_reached:
            raise RuntimeError("replan_limit_reached")
        cycle_record = _mapping(cycle)
        request = _mapping(replan_request) or _mapping(cycle_record.get("replan_request"))
        source_goal_id = _text(goal_id or cycle_record.get("goal_id") or request.get("goal_id"))
        resolved_cycle_index = int(cycle_index if cycle_index is not None else cycle_record.get("cycle_index") or 0)
        session_id = _text(cycle_record.get("session_id") or cycle_record.get("runtime_session_id"))
        task_id = f"replan:{source_goal_id}:{resolved_cycle_index}"
        replan_request_id = _text(request.get("request_id"), task_id)
        parent_lineage = extract_goal_lineage(cycle_record)
        lineage = extract_goal_lineage(
            {
                **parent_lineage,
                "goal_id": source_goal_id,
                "source_goal_id": source_goal_id,
                "branch_type": "replan",
                "branch_id": replan_request_id,
                "replan_request_id": replan_request_id,
            },
            require_complete=True,
        )
        evidence_refs = [
            _text(item.get("evidence_id"))
            for item in (request.get("evidence_chain") or [])
            if isinstance(item, Mapping) and _text(item.get("evidence_id"))
        ]
        record = attach_goal_lineage({
            "schema": ENGINEERING_REPLAN_RECORD_SCHEMA,
            "goal_id": source_goal_id,
            "task_id": task_id,
            "replan_request_id": replan_request_id,
            "source_goal_id": source_goal_id,
            "cycle_index": resolved_cycle_index,
            **({"session_id": session_id} if session_id else {}),
            "evidence_ref": evidence_refs[0] if evidence_refs else "",
            "evidence_refs": list(dict.fromkeys(evidence_refs)),
            "decision_evidence_id": "",
            "authority_state": "completion_authority_not_granted",
            "reason": _text(request.get("reason"), "recoverable_runtime_failure"),
            "replan_reason": _text(request.get("replan_reason") or request.get("reason"), "recoverable_runtime_failure"),
            "failed_step": _mapping(request.get("failed_step")),
            "missing_artifacts": _list(request.get("missing_artifacts")),
            "next_runtime_request": _mapping(request.get("next_runtime_request")),
            "replan_request": copy.deepcopy(request),
            "runner_adaptive_decision": _mapping(_mapping(runner_result).get("adaptive_decision")),
            "adaptive_planning_record": _mapping(
                _mapping(_mapping(runner_result).get("adaptive_decision")).get("adaptive_planning_record")
            ),
            "root_cause_report": _mapping(request.get("root_cause_report")),
            "evidence_chain": copy.deepcopy(request.get("evidence_chain") or []),
            "replan_coordinator": {
                "schema": REPLAN_COORDINATOR_SCHEMA,
                "created_replan_record": True,
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
        return record, runtime.record_replan(record)


__all__ = ["ENGINEERING_REPLAN_RECORD_SCHEMA", "REPLAN_COORDINATOR_SCHEMA", "ReplanCoordinator"]
