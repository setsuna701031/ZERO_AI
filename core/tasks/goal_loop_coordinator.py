from __future__ import annotations

"""Loop-intent coordinator for EngineeringGoalLoop.

GoalLoopCoordinator converts the passive AdaptiveReplanStateMachine result into
one coarse loop action.  It does not create records, persist state, execute
runtime work, mutate repositories, or write memory.
"""

import copy
from dataclasses import dataclass
from typing import Any, Mapping


GOAL_LOOP_COORDINATOR_SCHEMA = "zero.goal_loop_coordinator.v1"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


@dataclass(frozen=True)
class GoalLoopDecision:
    action: str
    terminal: bool
    stop_reason: str = ""
    refusal_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": GOAL_LOOP_COORDINATOR_SCHEMA,
            "action": self.action,
            "terminal": self.terminal,
            "stop_reason": self.stop_reason,
            "refusal_reason": self.refusal_reason,
            "execution_path": {
                "coordinator_only": True,
                "executes_tasks": False,
                "creates_continuation": False,
                "creates_replan": False,
                "persists_records": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


class GoalLoopCoordinator:
    """Classify state-machine output into loop orchestration intent."""

    def classify_state(self, state: Mapping[str, Any]) -> GoalLoopDecision:
        record = _mapping(state)
        if bool(record.get("creates_replan_record")):
            return GoalLoopDecision(
                action="create_replan_record",
                terminal=True,
                stop_reason=_text(record.get("stop_reason"), "replan"),
            )
        if bool(record.get("creates_continuation")):
            return GoalLoopDecision(action="create_continuation", terminal=False)
        stop_reason = _text(record.get("stop_reason"), _text(record.get("loop_action"), "stop"))
        refusal_reason = _text(record.get("refusal_reason"))
        if not bool(record.get("accepted")) or record.get("loop_action") in {"refuse", "stop", "wait_for_user"}:
            refusal_reason = refusal_reason or stop_reason
        return GoalLoopDecision(
            action="terminal",
            terminal=True,
            stop_reason=stop_reason,
            refusal_reason=refusal_reason,
        )


__all__ = ["GOAL_LOOP_COORDINATOR_SCHEMA", "GoalLoopCoordinator", "GoalLoopDecision"]
