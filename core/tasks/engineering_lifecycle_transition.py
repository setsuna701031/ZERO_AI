from __future__ import annotations

"""Transition contract for engineering lifecycle changes."""

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from core.tasks.engineering_lifecycle_state import clean_engineering_lifecycle_state


ENGINEERING_LIFECYCLE_TRANSITION_SCHEMA = "zero.engineering_lifecycle_transition.v1"


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


@dataclass(frozen=True)
class EngineeringLifecycleTransition:
    from_state: str
    to_state: str
    action: str
    reason: str = ""
    adaptive_loop_contract: Mapping[str, Any] | None = None
    adaptive_replan_state: Mapping[str, Any] | None = None
    completion_attestation: Any = None
    goal_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "from_state", clean_engineering_lifecycle_state(self.from_state))
        object.__setattr__(self, "to_state", clean_engineering_lifecycle_state(self.to_state))
        object.__setattr__(self, "action", _text(self.action, self.to_state))
        object.__setattr__(self, "reason", _text(self.reason, f"engineering_lifecycle_{self.action}"))
        object.__setattr__(
            self,
            "adaptive_loop_contract",
            copy.deepcopy(dict(self.adaptive_loop_contract)) if isinstance(self.adaptive_loop_contract, Mapping) else {},
        )
        object.__setattr__(
            self,
            "adaptive_replan_state",
            copy.deepcopy(dict(self.adaptive_replan_state)) if isinstance(self.adaptive_replan_state, Mapping) else {},
        )
        object.__setattr__(self, "goal_id", _text(self.goal_id))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_LIFECYCLE_TRANSITION_SCHEMA,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "action": self.action,
            "reason": self.reason,
            "adaptive_loop_contract": copy.deepcopy(dict(self.adaptive_loop_contract or {})),
            "adaptive_replan_state": copy.deepcopy(dict(self.adaptive_replan_state or {})),
            "goal_id": self.goal_id,
            "execution_path": {
                "contract_only": True,
                "executes_tasks": False,
                "persists_records": False,
                "mutates_goal_repository": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


__all__ = ["ENGINEERING_LIFECYCLE_TRANSITION_SCHEMA", "EngineeringLifecycleTransition"]
