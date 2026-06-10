from __future__ import annotations

"""State machine for loop-facing Adaptive Replan contracts.

The state machine owns only legality and normalized loop intent.  It does not
create continuation records, create replan records, persist evidence, execute
runtime actions, mutate goals, or write memory.
"""

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from core.adaptive.adaptive_replan_state import clean_adaptive_replan_state
from core.adaptive.adaptive_replan_transition import AdaptiveReplanTransition
from core.adaptive.adaptive_replan_validator import AdaptiveReplanValidator, TERMINAL_STATES


ADAPTIVE_REPLAN_STATE_MACHINE_SCHEMA = "zero.adaptive_replan_state_machine.v1"


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class AdaptiveReplanStateResult:
    accepted: bool
    from_state: str
    to_state: str
    loop_action: str
    terminal: bool
    stop_reason: str
    reason: str
    refusal_reason: str = ""
    creates_replan_record: bool = False
    creates_continuation: bool = False
    blocked_reason: str = ""
    contract: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ADAPTIVE_REPLAN_STATE_MACHINE_SCHEMA,
            "accepted": self.accepted,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "loop_action": self.loop_action,
            "terminal": self.terminal,
            "stop_reason": self.stop_reason,
            "reason": self.reason,
            "refusal_reason": self.refusal_reason,
            "creates_replan_record": self.creates_replan_record,
            "creates_continuation": self.creates_continuation,
            "blocked_reason": self.blocked_reason,
            "contract": copy.deepcopy(dict(self.contract or {})),
            "execution_path": {
                "decision_only": True,
                "executes_tasks": False,
                "persists_records": False,
                "mutates_goal_repository": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


class AdaptiveReplanStateMachine:
    def __init__(self, *, validator: AdaptiveReplanValidator | None = None) -> None:
        self.validator = validator or AdaptiveReplanValidator()

    def transition(self, transition: AdaptiveReplanTransition | Mapping[str, Any]) -> AdaptiveReplanStateResult:
        transition_record = transition.to_dict() if isinstance(transition, AdaptiveReplanTransition) else _mapping(transition)
        validation = self.validator.validate(transition_record)
        validation_record = validation.to_dict()
        contract = _mapping(transition_record.get("contract"))
        from_state = _text(validation_record.get("from_state"))
        to_state = _text(validation_record.get("to_state"))
        if not validation.accepted:
            return AdaptiveReplanStateResult(
                accepted=False,
                from_state=from_state,
                to_state=to_state,
                loop_action="stop",
                terminal=True,
                stop_reason="invalid_adaptive_replan_transition",
                refusal_reason="invalid_adaptive_replan_transition",
                reason=_text(validation_record.get("reason"), "invalid_adaptive_replan_transition"),
                blocked_reason=_text(validation_record.get("blocked_reason")),
                contract=contract,
            )
        return self._accepted_result(from_state=from_state, to_state=to_state, contract=contract)

    def evaluate_contract(self, contract: Mapping[str, Any], *, from_state: str = "continue") -> AdaptiveReplanStateResult:
        return self.transition(AdaptiveReplanTransition.from_contract(contract, from_state=from_state))

    def _accepted_result(self, *, from_state: str, to_state: str, contract: Mapping[str, Any]) -> AdaptiveReplanStateResult:
        action = clean_adaptive_replan_state(to_state)
        reason = _text(contract.get("reason"), f"adaptive_replan_{action}")
        stop_reason = _text(contract.get("stop_reason"))
        refusal_reason = _text(contract.get("refusal_reason"))
        return AdaptiveReplanStateResult(
            accepted=True,
            from_state=from_state,
            to_state=action,
            loop_action=action,
            terminal=action in TERMINAL_STATES,
            stop_reason=stop_reason or action if action in TERMINAL_STATES else "",
            refusal_reason=refusal_reason,
            reason=reason,
            creates_replan_record=bool(contract.get("creates_replan_record")) or action == "replan",
            creates_continuation=bool(contract.get("creates_continuation")) or action == "continue",
            contract=contract,
        )


__all__ = [
    "ADAPTIVE_REPLAN_STATE_MACHINE_SCHEMA",
    "AdaptiveReplanStateMachine",
    "AdaptiveReplanStateResult",
]
