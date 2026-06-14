from __future__ import annotations

"""Dispatch loop decisions to continuation/replan coordinators."""

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from core.adaptive.continuation_coordinator import ContinuationCoordinator
from core.adaptive.continuation_runtime import ContinuationRuntime
from core.adaptive.replan_coordinator import ReplanCoordinator
from core.adaptive.replan_runtime import ReplanRuntime
from core.goals.goal_completion_authority import is_accepted_goal_completion_result


GOAL_LOOP_DISPATCHER_SCHEMA = "zero.goal_loop_dispatcher.v1"


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


@dataclass(frozen=True)
class GoalLoopDispatchResult:
    action: str
    cycle: Mapping[str, Any]
    current_goal_id: str
    terminal: bool
    stop_reason: str = ""
    refusal_reason: str = ""
    continuation_runtime: ContinuationRuntime | None = None
    replan_runtime: ReplanRuntime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": GOAL_LOOP_DISPATCHER_SCHEMA,
            "action": self.action,
            "current_goal_id": self.current_goal_id,
            "terminal": self.terminal,
            "stop_reason": self.stop_reason,
            "refusal_reason": self.refusal_reason,
            "cycle": copy.deepcopy(dict(self.cycle)),
            "continuation_runtime": self.continuation_runtime.to_dict() if self.continuation_runtime else {},
            "replan_runtime": self.replan_runtime.to_dict() if self.replan_runtime else {},
            "execution_path": {
                "dispatcher_only": True,
                "executes_tasks": False,
                "decides_adaptive_action": False,
                "persists_records": False,
                "writes_evidence": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


class GoalLoopDispatcher:
    """Dispatch passive loop decisions without owning long-horizon state."""

    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        continuation_coordinator: ContinuationCoordinator | Any,
        replan_coordinator: ReplanCoordinator | Any,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else None
        self.continuation_coordinator = continuation_coordinator
        self.replan_coordinator = replan_coordinator

    def dispatch(
        self,
        *,
        loop_decision: Mapping[str, Any],
        cycle: Mapping[str, Any],
        current_goal_id: str,
        cycle_index: int,
        continuation_runtime: ContinuationRuntime,
        replan_runtime: ReplanRuntime,
    ) -> GoalLoopDispatchResult:
        decision = _mapping(loop_decision)
        updated_cycle = _mapping(cycle)
        action = _text(decision.get("action"), "terminal")

        if action == "create_replan_record":
            replan_record, next_replan_runtime = self.replan_coordinator.create_replan_record(
                runtime=replan_runtime,
                cycle=updated_cycle,
                goal_id=current_goal_id,
                cycle_index=cycle_index,
                replan_request=_mapping(updated_cycle.get("replan_request")),
                runner_result=_mapping(updated_cycle.get("runner_result")),
            )
            updated_cycle["replan_record"] = replan_record
            updated_cycle["goal_loop_dispatcher"] = self._marker(action="create_replan_record")
            return GoalLoopDispatchResult(
                action="create_replan_record",
                cycle=updated_cycle,
                current_goal_id=current_goal_id,
                terminal=True,
                stop_reason=_text(decision.get("stop_reason"), "replan"),
                continuation_runtime=continuation_runtime,
                replan_runtime=next_replan_runtime,
            )

        if action == "create_continuation":
            work_item, next_continuation_runtime = self.continuation_coordinator.create_work_item(
                runtime=continuation_runtime,
                cycle=updated_cycle,
                goal_id=current_goal_id,
                cycle_index=cycle_index,
                continuation_plan=_mapping(updated_cycle.get("continuation_plan")),
                runner_result=_mapping(updated_cycle.get("runner_result")),
            )
            updated_cycle["continuation_work_item"] = work_item
            updated_cycle["goal_loop_dispatcher"] = self._marker(action="create_continuation")
            return GoalLoopDispatchResult(
                action="create_continuation",
                cycle=updated_cycle,
                current_goal_id=_text(next_continuation_runtime.current_goal_id, current_goal_id),
                terminal=False,
                continuation_runtime=next_continuation_runtime,
                replan_runtime=replan_runtime,
            )

        stop_reason = _text(decision.get("stop_reason"), "stop")
        refusal_reason = _text(decision.get("refusal_reason"))

        if self._is_complete_terminal(decision=decision, cycle=updated_cycle) and not self._completion_authority_accepted(
            updated_cycle,
            goal_id=current_goal_id,
        ):
            updated_cycle["goal_loop_dispatcher"] = self._marker(
                action="terminal_blocked",
                reason="goal_completion_authority_required",
            )
            updated_cycle["goal_completion_authority_required"] = True
            return GoalLoopDispatchResult(
                action="terminal_blocked",
                cycle=updated_cycle,
                current_goal_id=current_goal_id,
                terminal=False,
                stop_reason="goal_completion_authority_required",
                refusal_reason=refusal_reason,
                continuation_runtime=continuation_runtime,
                replan_runtime=replan_runtime,
            )

        updated_cycle["goal_loop_dispatcher"] = self._marker(action="terminal")
        return GoalLoopDispatchResult(
            action="terminal",
            cycle=updated_cycle,
            current_goal_id=current_goal_id,
            terminal=True,
            stop_reason=stop_reason,
            refusal_reason=refusal_reason,
            continuation_runtime=continuation_runtime,
            replan_runtime=replan_runtime,
        )

    @staticmethod
    def _is_complete_terminal(*, decision: Mapping[str, Any], cycle: Mapping[str, Any]) -> bool:
        action = _text(decision.get("action"), "terminal")
        stop_reason = _text(decision.get("stop_reason")).lower()
        decision_name = _text(decision.get("decision") or cycle.get("adaptive_decision")).lower()
        adaptive_record = _mapping(cycle.get("adaptive_decision_record"))
        adaptive_decision = _text(adaptive_record.get("decision")).lower()

        return (
            action == "terminal"
            and (
                stop_reason == "complete"
                or decision_name == "complete"
                or adaptive_decision == "complete"
            )
        )

    @staticmethod
    def _completion_authority_accepted(cycle: Mapping[str, Any], *, goal_id: str) -> bool:
        return is_accepted_goal_completion_result(cycle.get("goal_completion_attestation"), goal_id=goal_id)

    @staticmethod
    def _marker(*, action: str, reason: str = "") -> dict[str, Any]:
        marker = {
            "schema": GOAL_LOOP_DISPATCHER_SCHEMA,
            "dispatched_action": action,
            "requires_goal_completion_authority_for_complete_terminal": True,
            "execution_path": {
                "dispatcher_only": True,
                "executes_tasks": False,
                "decides_adaptive_action": False,
                "persists_records": False,
                "writes_evidence": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }
        if reason:
            marker["reason"] = reason
        return marker


__all__ = ["GOAL_LOOP_DISPATCHER_SCHEMA", "GoalLoopDispatcher", "GoalLoopDispatchResult"]
