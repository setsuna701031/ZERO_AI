from __future__ import annotations

"""Long horizon loop for persisted engineering goals.

EngineeringGoalLoop owns only the cycle around EngineeringGoalRunner results.
It does not execute tasks, plan work, mutate runtime internals, or enter the
RuntimeOrchestrator.
"""

import copy
import time
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_goal_runner import EngineeringGoalRunner
from core.tasks.engineering_issue_summary import apply_engineering_issue_summary


ENGINEERING_GOAL_LOOP_SCHEMA = "zero.engineering_goal_loop.v1"
ENGINEERING_GOAL_LOOP_CYCLE_SCHEMA = "zero.engineering_goal_loop.cycle.v1"
ENGINEERING_CONTINUATION_WORK_ITEM_SCHEMA = "zero.engineering_goal_loop.continuation_work_item.v2"
ENGINEERING_REPLAN_RECORD_SCHEMA = "zero.engineering_goal_loop.replan_record.v2"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


class EngineeringGoalLoop:
    """Run one engineering goal across bounded adaptive continuation cycles."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        repository: EngineeringGoalRepository | Any | None = None,
        runner: EngineeringGoalRunner | Any | None = None,
        issue_reporter: Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.repository = repository or EngineeringGoalRepository(self.repo_root)
        self.issue_reporter = issue_reporter
        self.runner = runner or EngineeringGoalRunner(
            repo_root=self.repo_root,
            repository=self.repository,
            issue_reporter=self.issue_reporter,
        )
        self._last_cycle: dict[str, Any] = {}

    def run_until_terminal(self, goal_id: str, max_cycles: int = 3) -> dict[str, Any]:
        target_goal_id = _clean_text(goal_id)
        cycle_limit = max(1, int(max_cycles or 1))
        cycles: list[dict[str, Any]] = []
        current_goal_id = target_goal_id
        terminal = False
        stop_reason = "max_cycles_reached"

        for cycle_index in range(cycle_limit):
            cycle = self.run_one_cycle(current_goal_id, cycle_index=cycle_index)
            cycles.append(cycle)
            decision = _clean_text(cycle.get("adaptive_decision")).lower()

            if self.stop_on_complete(cycle):
                terminal = True
                stop_reason = "complete"
                break

            if self.stop_on_blocked(cycle):
                terminal = True
                stop_reason = "blocked"
                break

            if decision == "replan":
                cycle["replan_record"] = self.create_replan_record(
                    goal_id=current_goal_id,
                    cycle_index=cycle_index,
                    replan_request=_as_mapping(cycle.get("replan_request")),
                    runner_result=_as_mapping(cycle.get("runner_result")),
                )
                terminal = True
                stop_reason = "replan"
                break

            if decision != "continue":
                terminal = True
                stop_reason = "non_continuable_adaptive_decision"
                break

            work_item = self.create_continuation_work_item(
                goal_id=current_goal_id,
                cycle_index=cycle_index,
                continuation_plan=_as_mapping(cycle.get("continuation_plan")),
                runner_result=_as_mapping(cycle.get("runner_result")),
            )
            cycle["continuation_work_item"] = work_item
            current_goal_id = _clean_text(work_item.get("goal_id"), current_goal_id)

        latest_decision = _as_mapping(cycles[-1].get("adaptive_decision_record")) if cycles else {}
        return apply_engineering_issue_summary(
            {
            "schema": ENGINEERING_GOAL_LOOP_SCHEMA,
            "ok": terminal and bool(cycles) and _clean_text(latest_decision.get("decision")) == "complete",
            "mode": "engineering_goal_loop",
            "goal_id": target_goal_id,
            "current_goal_id": current_goal_id,
            "terminal": terminal,
            "stop_reason": stop_reason,
            "adaptive_decision": copy.deepcopy(latest_decision),
            "adaptive_reason": _clean_text(latest_decision.get("reason")),
            "adaptive_confidence": latest_decision.get("confidence", 0.0),
            "adaptive_confidence_score": copy.deepcopy(_as_mapping(latest_decision.get("confidence_score"))),
            "adaptive_evidence_chain": copy.deepcopy(latest_decision.get("evidence_chain") or []),
            "root_cause_report": copy.deepcopy(_as_mapping(latest_decision.get("root_cause_report"))),
            "max_cycles": cycle_limit,
            "cycle_count": len(cycles),
            "cycles": cycles,
            "execution_path": {
                "route": "Goal -> Adaptive Planner -> Runtime",
                "program_id": "",
                "portfolio_id": "",
                "goal_id": target_goal_id,
                "goal_loop_owns_long_horizon_cycles": True,
                "runner_owns_runtime_bridge": True,
                "adaptive_planner_decides_only": True,
                "runtime_orchestrator_embedded_here": False,
                "direct_execution": False,
                "memory_persistence_owned_here": False,
                "unbounded_loop": False,
            },
            "updated_at": time.time(),
            },
            repo_root=self.repo_root,
            issue_reporter=self.issue_reporter,
        )

    def run_one_cycle(self, goal_id: str, *, cycle_index: int = 0) -> dict[str, Any]:
        runner_result = self.runner.run_goal(_clean_text(goal_id))
        runtime_result = _as_mapping(runner_result.get("runtime_result"))
        adaptive = _as_mapping(runner_result.get("adaptive_decision"))
        decision = _clean_text(adaptive.get("decision"))
        root_cause = _as_mapping(adaptive.get("root_cause") or runner_result.get("runtime_root_cause"))
        cycle = {
            "schema": ENGINEERING_GOAL_LOOP_CYCLE_SCHEMA,
            "cycle_index": int(cycle_index),
            "goal_id": _clean_text(runner_result.get("goal_id"), _clean_text(goal_id)),
            "ok": bool(runner_result.get("ok")),
            "runtime_state": _clean_text(runtime_result.get("state")),
            "adaptive_decision": decision,
            "adaptive_decision_record": copy.deepcopy(adaptive),
            "adaptive_reason": _clean_text(adaptive.get("reason")),
            "adaptive_confidence": adaptive.get("confidence", 0.0),
            "adaptive_confidence_score": copy.deepcopy(_as_mapping(adaptive.get("confidence_score"))),
            "adaptive_evidence_chain": copy.deepcopy(adaptive.get("evidence_chain") or []),
            "root_cause_report": copy.deepcopy(_as_mapping(adaptive.get("root_cause_report"))),
            "continuation_plan": copy.deepcopy(_as_mapping(adaptive.get("continuation_plan"))),
            "replan_request": copy.deepcopy(_as_mapping(adaptive.get("replan_request"))),
            "runner_result": copy.deepcopy(dict(runner_result)) if isinstance(runner_result, Mapping) else {},
            "continuation_work_item": {},
            "replan_record": {},
            "updated_at": time.time(),
        }
        if decision == "blocked":
            cycle["root_cause"] = root_cause
        self._last_cycle = copy.deepcopy(cycle)
        return cycle

    def create_continuation_work_item(
        self,
        *,
        goal_id: str = "",
        cycle_index: int | None = None,
        continuation_plan: Mapping[str, Any] | None = None,
        runner_result: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_cycle = _as_mapping(self._last_cycle)
        plan = _as_mapping(continuation_plan) or _as_mapping(last_cycle.get("continuation_plan"))
        next_request = _as_mapping(plan.get("next_runtime_request"))
        payload = _as_mapping(next_request.get("payload"))
        work_item_template = _as_mapping(plan.get("work_item_template"))
        source_goal_id = _clean_text(goal_id or last_cycle.get("goal_id") or plan.get("goal_id") or next_request.get("goal_id"))
        resolved_cycle_index = int(cycle_index if cycle_index is not None else last_cycle.get("cycle_index") or 0)
        continuation_goal_id = self._continuation_goal_id(source_goal_id, resolved_cycle_index)
        summary = _clean_text(payload.get("goal") or plan.get("reason"), f"Continue {source_goal_id}")
        payload["goal_id"] = continuation_goal_id
        payload["task_id"] = continuation_goal_id
        payload["package_id"] = continuation_goal_id
        payload["source_goal_id"] = source_goal_id
        payload["continuation_source_goal_id"] = source_goal_id
        payload["continuation_cycle_index"] = resolved_cycle_index
        payload["continuation_requested"] = True
        payload["continuation_objective"] = _clean_text(work_item_template.get("objective"), summary)
        payload["continuation_acceptance"] = _as_mapping(work_item_template.get("acceptance"))
        payload["adaptive_evidence_chain"] = copy.deepcopy(plan.get("evidence_chain") or [])

        record = self.repository.save_goal(
            {
                "schema": ENGINEERING_CONTINUATION_WORK_ITEM_SCHEMA,
                "goal_id": continuation_goal_id,
                "summary": summary,
                "status": "pending",
                "priority": 0.0,
                "payload": payload,
                "metadata": {
                    "source": "engineering_goal_loop",
                    "source_goal_id": source_goal_id,
                    "source_cycle_index": resolved_cycle_index,
                    "continuation_plan": plan,
                    "work_item_template": work_item_template,
                    "adaptive_evidence_chain": copy.deepcopy(plan.get("evidence_chain") or []),
                    "runner_adaptive_decision": _as_mapping(_as_mapping(runner_result).get("adaptive_decision")),
                },
            }
        )
        return {
            "schema": ENGINEERING_CONTINUATION_WORK_ITEM_SCHEMA,
            "goal_id": record["goal_id"],
            "source_goal_id": source_goal_id,
            "cycle_index": resolved_cycle_index,
            "record": record,
            "created_at": time.time(),
        }

    def create_replan_record(
        self,
        *,
        goal_id: str = "",
        cycle_index: int | None = None,
        replan_request: Mapping[str, Any] | None = None,
        runner_result: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_cycle = _as_mapping(self._last_cycle)
        request = _as_mapping(replan_request) or _as_mapping(last_cycle.get("replan_request"))
        source_goal_id = _clean_text(goal_id or last_cycle.get("goal_id") or request.get("goal_id"))
        resolved_cycle_index = int(cycle_index if cycle_index is not None else last_cycle.get("cycle_index") or 0)
        return {
            "schema": ENGINEERING_REPLAN_RECORD_SCHEMA,
            "goal_id": source_goal_id,
            "cycle_index": resolved_cycle_index,
            "reason": _clean_text(request.get("reason"), "recoverable_runtime_failure"),
            "replan_request": copy.deepcopy(request),
            "runner_adaptive_decision": _as_mapping(_as_mapping(runner_result).get("adaptive_decision")),
            "root_cause_report": _as_mapping(request.get("root_cause_report")),
            "evidence_chain": copy.deepcopy(request.get("evidence_chain") or []),
            "created_at": time.time(),
        }

    def stop_on_complete(self, cycle: Mapping[str, Any]) -> bool:
        return _clean_text(cycle.get("adaptive_decision")).lower() == "complete"

    def stop_on_blocked(self, cycle: Mapping[str, Any]) -> bool:
        return _clean_text(cycle.get("adaptive_decision")).lower() == "blocked"

    def _continuation_goal_id(self, source_goal_id: str, cycle_index: int) -> str:
        base = f"{_clean_text(source_goal_id, 'goal')}__continuation_{int(cycle_index) + 1}"
        candidate = base
        suffix = 2
        while self.repository.load_goal(candidate) is not None:
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate


__all__ = [
    "ENGINEERING_CONTINUATION_WORK_ITEM_SCHEMA",
    "ENGINEERING_GOAL_LOOP_CYCLE_SCHEMA",
    "ENGINEERING_GOAL_LOOP_SCHEMA",
    "ENGINEERING_REPLAN_RECORD_SCHEMA",
    "EngineeringGoalLoop",
]
