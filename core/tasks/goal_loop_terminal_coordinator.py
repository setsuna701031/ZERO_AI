from __future__ import annotations

"""Terminal result builder for EngineeringGoalLoop.

GoalLoopTerminalCoordinator owns only final result assembly. It does not run
cycles, dispatch coordinators, persist records, mutate goals, write evidence, or
write memory.

EngineeringGoalLoop may only return ok=True when the latest cycle carries an
accepted GoalCompletionAuthority result. A terminal/complete adaptive decision
alone is not enough to declare Engineering Goal Loop success.
"""

import copy
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from core.tasks.adaptive_planning_contract import adaptive_planning_ownership_contract
from core.tasks.engineering_issue_summary import apply_engineering_issue_summary


GOAL_LOOP_TERMINAL_COORDINATOR_SCHEMA = "zero.goal_loop_terminal_coordinator.v1"
ENGINEERING_GOAL_LOOP_SCHEMA = "zero.engineering_goal_loop.v1"


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


class GoalLoopTerminalCoordinator:
    """Build the final EngineeringGoalLoop return payload."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        issue_reporter: Any | None = None,
        evidence_chain_summary: Callable[[str], Mapping[str, Any]] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.issue_reporter = issue_reporter
        self.evidence_chain_summary = evidence_chain_summary

    def build_result(
        self,
        *,
        target_goal_id: str,
        current_goal_id: str,
        terminal: bool,
        stop_reason: str,
        refusal_reason: str = "",
        cycles: Sequence[Mapping[str, Any]] | None = None,
        max_cycles: int = 1,
        max_replans: int = 0,
        max_continuations: int = 0,
        session_runtime: Any | None = None,
        continuation_runtime: Any | None = None,
        replan_runtime: Any | None = None,
    ) -> dict[str, Any]:
        cycle_records = [copy.deepcopy(dict(cycle)) for cycle in cycles or [] if isinstance(cycle, Mapping)]
        latest_cycle = _mapping(cycle_records[-1]) if cycle_records else {}
        latest_decision = _mapping(latest_cycle.get("adaptive_decision_record"))
        goal_completion_authority_result = self._goal_completion_authority_result(latest_cycle)

        continuation_runtime_record = self._to_dict(continuation_runtime)
        replan_runtime_record = self._to_dict(replan_runtime)
        session_runtime_record = self._to_dict(session_runtime)

        replan_count = int(replan_runtime_record.get("replan_count") or latest_cycle.get("replan_count") or 0)
        continuation_count = int(
            continuation_runtime_record.get("continuation_count") or latest_cycle.get("continuation_count") or 0
        )

        adaptive_complete = _text(latest_decision.get("decision")) == "complete"
        completion_authority_accepted = self._completion_authority_accepted(goal_completion_authority_result)
        ok = bool(terminal and cycle_records and adaptive_complete and completion_authority_accepted)

        effective_stop_reason = _text(stop_reason, "stop")
        if terminal and cycle_records and adaptive_complete and not completion_authority_accepted:
            effective_stop_reason = "goal_completion_authority_required"

        payload = {
            "schema": ENGINEERING_GOAL_LOOP_SCHEMA,
            "ok": ok,
            "mode": "engineering_goal_loop",
            "goal_id": _text(target_goal_id),
            "current_goal_id": _text(current_goal_id, _text(target_goal_id)),
            "terminal": bool(terminal),
            "stop_reason": effective_stop_reason,
            "adaptive_decision": copy.deepcopy(latest_decision),
            "goal_completion_authority_result": copy.deepcopy(goal_completion_authority_result),
            "adaptive_replan_contract": copy.deepcopy(_mapping(latest_cycle.get("adaptive_replan_contract"))),
            "adaptive_replan_state": copy.deepcopy(_mapping(latest_cycle.get("adaptive_replan_state"))),
            "adaptive_observation": copy.deepcopy(_mapping(latest_cycle.get("adaptive_observation"))),
            "adaptive_delta": copy.deepcopy(_mapping(latest_cycle.get("adaptive_delta"))),
            "adaptive_loop_contract": copy.deepcopy(_mapping(latest_cycle.get("adaptive_loop_contract"))),
            "engineering_lifecycle_state": copy.deepcopy(_mapping(latest_cycle.get("engineering_lifecycle_state"))),
            "engineering_session_state": copy.deepcopy(_mapping(latest_cycle.get("engineering_session_state"))),
            "engineering_program_state": copy.deepcopy(_mapping(latest_cycle.get("engineering_program_state"))),
            "goal_loop_decision": copy.deepcopy(_mapping(latest_cycle.get("goal_loop_decision"))),
            "adaptive_reason": _text(latest_decision.get("reason")),
            "adaptive_confidence": latest_decision.get("confidence", 0.0),
            "adaptive_confidence_score": copy.deepcopy(_mapping(latest_decision.get("confidence_score"))),
            "adaptive_evidence_chain": copy.deepcopy(latest_decision.get("evidence_chain") or []),
            "evidence_chain": self._evidence_summary(_text(target_goal_id)),
            "root_cause_report": copy.deepcopy(_mapping(latest_decision.get("root_cause_report"))),
            "max_cycles": int(max_cycles),
            "max_replans": int(max_replans),
            "max_continuations": int(max_continuations),
            "replan_count": replan_count,
            "continuation_count": continuation_count,
            "adaptive_refusal_reason": _text(refusal_reason),
            "cycle_count": len(cycle_records),
            "engineering_session_runtime": session_runtime_record,
            "continuation_runtime": continuation_runtime_record,
            "replan_runtime": replan_runtime_record,
            "cycles": cycle_records,
            "goal_loop_terminal_coordinator": {
                "schema": GOAL_LOOP_TERMINAL_COORDINATOR_SCHEMA,
                "built_terminal_result": True,
                "requires_goal_completion_authority": True,
                "goal_completion_authority_accepted": completion_authority_accepted,
                "execution_path": {
                    "terminal_assembly_only": True,
                    "executes_tasks": False,
                    "dispatches_cycles": False,
                    "persists_records": False,
                    "writes_evidence": False,
                    "mutates_runtime": False,
                    "mutates_memory": False,
                },
            },
            "execution_path": {
                "route": "Goal -> Adaptive Planner -> GoalCompletionAuthority -> Runtime",
                "adaptive_planning_ownership_contract": adaptive_planning_ownership_contract(),
                "program_id": "",
                "portfolio_id": "",
                "goal_id": _text(target_goal_id),
                "goal_loop_owns_long_horizon_cycles": True,
                "runner_owns_runtime_bridge": True,
                "adaptive_planner_decides_only": True,
                "goal_loop_consumes_replan_contract_only": True,
                "goal_loop_consumes_replan_state_machine": True,
                "goal_loop_consumes_runtime_contract": True,
                "goal_loop_builds_adaptive_observations": True,
                "goal_loop_compares_adaptive_deltas": True,
                "goal_loop_consumes_adaptive_loop_contract": True,
                "goal_loop_consumes_engineering_lifecycle_state_machine": True,
                "goal_loop_uses_adaptive_loop_coordinator": True,
                "goal_loop_uses_lifecycle_coordinator": True,
                "goal_loop_uses_goal_loop_coordinator": True,
                "goal_loop_consumes_engineering_session_state_machine": True,
                "goal_loop_uses_session_coordinator": True,
                "goal_loop_consumes_engineering_program_state_machine": True,
                "goal_loop_uses_program_coordinator": True,
                "goal_loop_uses_session_progression_coordinator": True,
                "goal_loop_uses_continuation_coordinator": True,
                "goal_loop_uses_replan_coordinator": True,
                "goal_loop_uses_goal_loop_dispatcher": True,
                "goal_loop_uses_terminal_coordinator": True,
                "goal_loop_requires_goal_completion_authority": True,
                "goal_loop_owns_continuation_creation": False,
                "goal_loop_owns_replan_creation": False,
                "goal_loop_owns_terminal_result_assembly": False,
                "runtime_orchestrator_embedded_here": False,
                "direct_execution": False,
                "memory_persistence_owned_here": False,
                "unbounded_loop": False,
            },
            "updated_at": time.time(),
        }
        return apply_engineering_issue_summary(
            payload,
            repo_root=self.repo_root,
            issue_reporter=self.issue_reporter,
        )

    def _evidence_summary(self, goal_id: str) -> dict[str, Any]:
        if not callable(self.evidence_chain_summary):
            return {}
        try:
            return copy.deepcopy(dict(self.evidence_chain_summary(goal_id)))
        except Exception:
            return {}

    @staticmethod
    def _goal_completion_authority_result(cycle: Mapping[str, Any]) -> dict[str, Any]:
        direct = _mapping(cycle.get("goal_completion_authority_result"))
        if direct:
            return direct

        decision = _mapping(cycle.get("adaptive_decision_record"))
        nested = _mapping(decision.get("goal_completion_authority_result"))
        if nested:
            return nested

        transition = _mapping(decision.get("required_transition"))
        transition_authority = _text(transition.get("completion_authority"))
        if transition_authority == "GoalCompletionAuthority":
            return {
                "accepted": True,
                "completed": transition.get("to_state") == "completed",
                "from_state": transition.get("from_state"),
                "to_state": transition.get("to_state"),
                "reason": transition.get("reason"),
                "evidence_refs": copy.deepcopy(transition.get("evidence_refs") or []),
                "source": "adaptive_decision_required_transition",
            }

        return {}

    @staticmethod
    def _completion_authority_accepted(result: Mapping[str, Any]) -> bool:
        if not isinstance(result, Mapping):
            return False
        return bool(result.get("accepted") is True and result.get("completed") is not False)

    @staticmethod
    def _to_dict(value: Any) -> dict[str, Any]:
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            return copy.deepcopy(dict(to_dict()))
        return _mapping(value)


__all__ = ["GOAL_LOOP_TERMINAL_COORDINATOR_SCHEMA", "GoalLoopTerminalCoordinator"]
