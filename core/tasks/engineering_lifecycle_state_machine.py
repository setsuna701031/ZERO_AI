from __future__ import annotations

"""State machine mapping Adaptive Loop v2 into engineering lifecycle state.

The state machine consumes passive contracts only. It does not create work,
execute runtime actions, persist records, mutate goals, write evidence, or touch
memory.
"""

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from core.tasks.engineering_lifecycle_state import TERMINAL_ENGINEERING_LIFECYCLE_STATES, clean_engineering_lifecycle_state
from core.tasks.engineering_lifecycle_transition import EngineeringLifecycleTransition
from core.tasks.engineering_lifecycle_validator import EngineeringLifecycleValidator


ENGINEERING_LIFECYCLE_STATE_MACHINE_SCHEMA = "zero.engineering_lifecycle_state_machine.v1"


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class EngineeringLifecycleStateResult:
    accepted: bool
    from_state: str
    to_state: str
    lifecycle_state: str
    terminal: bool
    reason: str
    blocked_reason: str = ""
    adaptive_loop_contract: Mapping[str, Any] | None = None
    adaptive_replan_state: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_LIFECYCLE_STATE_MACHINE_SCHEMA,
            "accepted": self.accepted,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "lifecycle_state": self.lifecycle_state,
            "terminal": self.terminal,
            "reason": self.reason,
            "blocked_reason": self.blocked_reason,
            "adaptive_loop_contract": copy.deepcopy(dict(self.adaptive_loop_contract or {})),
            "adaptive_replan_state": copy.deepcopy(dict(self.adaptive_replan_state or {})),
            "execution_path": {
                "state_machine_only": True,
                "executes_tasks": False,
                "creates_continuation": False,
                "creates_replan": False,
                "persists_records": False,
                "mutates_goal_repository": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


class EngineeringLifecycleStateMachine:
    def __init__(self, *, validator: EngineeringLifecycleValidator | None = None) -> None:
        self.validator = validator or EngineeringLifecycleValidator()

    def transition(self, transition: EngineeringLifecycleTransition | Mapping[str, Any]) -> EngineeringLifecycleStateResult:
        record = transition.to_dict() if isinstance(transition, EngineeringLifecycleTransition) else _mapping(transition)
        validation = self.validator.validate(record)
        validation_record = validation.to_dict()
        from_state = _text(validation_record.get("from_state"))
        to_state = _text(validation_record.get("to_state"))
        adaptive_loop_contract = _mapping(record.get("adaptive_loop_contract"))
        adaptive_replan_state = _mapping(record.get("adaptive_replan_state"))
        if not validation.accepted:
            return EngineeringLifecycleStateResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                lifecycle_state=from_state or "failed",
                terminal=True,
                reason=_text(validation_record.get("reason"), "engineering_lifecycle_transition_rejected"),
                blocked_reason=_text(validation_record.get("blocked_reason")),
                adaptive_loop_contract=adaptive_loop_contract,
                adaptive_replan_state=adaptive_replan_state,
            )
        return EngineeringLifecycleStateResult(
            accepted=True,
            from_state=from_state,
            to_state=to_state,
            lifecycle_state=to_state,
            terminal=to_state in TERMINAL_ENGINEERING_LIFECYCLE_STATES,
            reason=_text(record.get("reason"), _text(validation_record.get("reason"), f"engineering_lifecycle_{to_state}")),
            adaptive_loop_contract=adaptive_loop_contract,
            adaptive_replan_state=adaptive_replan_state,
        )

    def evaluate_adaptive_loop(
        self,
        adaptive_loop_contract: Mapping[str, Any],
        *,
        adaptive_replan_state: Mapping[str, Any] | None = None,
        from_state: str = "created",
    ) -> EngineeringLifecycleStateResult:
        loop_contract = _mapping(adaptive_loop_contract)
        replan_state = _mapping(adaptive_replan_state) or _mapping(loop_contract.get("adaptive_replan_state"))
        target = self.target_state_for_contract(loop_contract, adaptive_replan_state=replan_state)
        return self.transition(
            EngineeringLifecycleTransition(
                from_state=from_state,
                to_state=target,
                action=target,
                reason=_text(loop_contract.get("reason") or replan_state.get("reason"), f"engineering_lifecycle_{target}"),
                adaptive_loop_contract=loop_contract,
                adaptive_replan_state=replan_state,
            )
        )

    def evaluate_cycle(self, cycle: Mapping[str, Any], *, from_state: str = "created") -> EngineeringLifecycleStateResult:
        record = _mapping(cycle)
        return self.evaluate_adaptive_loop(
            _mapping(record.get("adaptive_loop_contract")),
            adaptive_replan_state=_mapping(record.get("adaptive_replan_state")),
            from_state=from_state,
        )

    @staticmethod
    def target_state_for_contract(
        adaptive_loop_contract: Mapping[str, Any],
        *,
        adaptive_replan_state: Mapping[str, Any] | None = None,
    ) -> str:
        loop = _mapping(adaptive_loop_contract)
        replan = _mapping(adaptive_replan_state) or _mapping(loop.get("adaptive_replan_state"))
        action = _text(replan.get("loop_action")).lower()
        loop_state = _text(loop.get("loop_state")).lower()

        if action == "complete":
            return "completed"
        if action == "blocked":
            return "blocked"
        if action in {"refuse", "stop"}:
            return "failed"
        if action == "wait_for_user":
            return "waiting_evidence"
        if bool(replan.get("creates_replan_record")) or action == "replan":
            return "replanning"
        if bool(replan.get("creates_continuation")) or bool(loop.get("next_cycle_allowed")) or action == "continue":
            return "continuing"
        if loop_state == "regressed":
            return "replanning"
        if loop_state == "stalled":
            return "waiting_evidence"
        if loop_state == "terminal":
            return "failed"
        return "running"


__all__ = [
    "ENGINEERING_LIFECYCLE_STATE_MACHINE_SCHEMA",
    "EngineeringLifecycleStateMachine",
    "EngineeringLifecycleStateResult",
]
