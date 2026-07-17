from __future__ import annotations

"""Transition contract for adaptive replan loop state changes."""

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from core.adaptive.adaptive_replan_state import clean_adaptive_replan_state


ADAPTIVE_REPLAN_TRANSITION_SCHEMA = "zero.adaptive_replan_transition.v1"


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


@dataclass(frozen=True)
class AdaptiveReplanTransition:
    from_state: str
    to_state: str
    action: str
    reason: str = ""
    contract: Mapping[str, Any] | None = None
    goal_id: str = ""
    completion_attestation: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "from_state", clean_adaptive_replan_state(self.from_state))
        object.__setattr__(self, "to_state", clean_adaptive_replan_state(self.to_state))
        object.__setattr__(self, "action", clean_adaptive_replan_state(self.action))
        object.__setattr__(self, "reason", _text(self.reason, f"adaptive_replan_{self.action}"))
        object.__setattr__(self, "contract", copy.deepcopy(dict(self.contract)) if isinstance(self.contract, Mapping) else {})
        object.__setattr__(self, "goal_id", _text(self.goal_id))

    @classmethod
    def from_contract(
        cls,
        contract: Mapping[str, Any],
        *,
        from_state: str = "continue",
        goal_id: str = "",
        completion_attestation: Any = None,
    ) -> "AdaptiveReplanTransition":
        record = copy.deepcopy(dict(contract)) if isinstance(contract, Mapping) else {}
        action = _text(record.get("loop_action"), "stop")
        reason = _text(record.get("reason") or record.get("stop_reason"), f"adaptive_replan_{action}")
        return cls(
            from_state=from_state,
            to_state=action,
            action=action,
            reason=reason,
            contract=record,
            goal_id=goal_id,
            completion_attestation=completion_attestation,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ADAPTIVE_REPLAN_TRANSITION_SCHEMA,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "action": self.action,
            "reason": self.reason,
            "contract": copy.deepcopy(dict(self.contract or {})),
            "goal_id": self.goal_id,
            "execution_path": {
                "decision_only": True,
                "executes_tasks": False,
                "persists_records": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


__all__ = ["ADAPTIVE_REPLAN_TRANSITION_SCHEMA", "AdaptiveReplanTransition"]
