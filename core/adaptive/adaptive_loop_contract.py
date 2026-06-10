from __future__ import annotations

"""Loop-facing contract that joins observation, delta, and replan state.

AdaptiveLoopContract is a passive audit/control boundary.  It does not execute
runtime work, create continuation records, persist evidence, mutate goals, or
write memory.
"""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.adaptive.adaptive_loop_state import classify_adaptive_loop_state


ADAPTIVE_LOOP_CONTRACT_SCHEMA = "zero.adaptive_loop.contract.v2"


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


@dataclass(frozen=True)
class AdaptiveLoopContract:
    goal_id: str
    cycle_index: int
    loop_state: str
    observation: Mapping[str, Any] = field(default_factory=dict)
    delta: Mapping[str, Any] = field(default_factory=dict)
    adaptive_replan_contract: Mapping[str, Any] = field(default_factory=dict)
    adaptive_replan_state: Mapping[str, Any] = field(default_factory=dict)
    terminal: bool = False
    next_cycle_allowed: bool = False
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "goal_id", _text(self.goal_id, "goal"))
        object.__setattr__(self, "cycle_index", max(0, int(self.cycle_index or 0)))
        object.__setattr__(self, "loop_state", _text(self.loop_state, "initial"))
        object.__setattr__(self, "observation", _mapping(self.observation))
        object.__setattr__(self, "delta", _mapping(self.delta))
        object.__setattr__(self, "adaptive_replan_contract", _mapping(self.adaptive_replan_contract))
        object.__setattr__(self, "adaptive_replan_state", _mapping(self.adaptive_replan_state))
        object.__setattr__(self, "terminal", bool(self.terminal))
        object.__setattr__(self, "next_cycle_allowed", bool(self.next_cycle_allowed))
        object.__setattr__(self, "reason", _text(self.reason, self.loop_state))

    @classmethod
    def from_cycle(cls, cycle: Mapping[str, Any]) -> "AdaptiveLoopContract":
        record = _mapping(cycle)
        observation = _mapping(record.get("adaptive_observation"))
        delta = _mapping(record.get("adaptive_delta"))
        replan_state = _mapping(record.get("adaptive_replan_state"))
        loop_state = classify_adaptive_loop_state(delta=delta, replan_state=replan_state)
        terminal = bool(replan_state.get("terminal"))
        next_cycle_allowed = bool(replan_state.get("creates_continuation")) and not terminal
        return cls(
            goal_id=_text(record.get("goal_id") or observation.get("goal_id")),
            cycle_index=int(record.get("cycle_index") or observation.get("cycle_index") or 0),
            loop_state=loop_state,
            observation=observation,
            delta=delta,
            adaptive_replan_contract=_mapping(record.get("adaptive_replan_contract")),
            adaptive_replan_state=replan_state,
            terminal=terminal,
            next_cycle_allowed=next_cycle_allowed,
            reason=_text(delta.get("reason") or replan_state.get("reason") or loop_state),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ADAPTIVE_LOOP_CONTRACT_SCHEMA,
            "goal_id": self.goal_id,
            "cycle_index": self.cycle_index,
            "loop_state": self.loop_state,
            "observation": copy.deepcopy(dict(self.observation)),
            "delta": copy.deepcopy(dict(self.delta)),
            "adaptive_replan_contract": copy.deepcopy(dict(self.adaptive_replan_contract)),
            "adaptive_replan_state": copy.deepcopy(dict(self.adaptive_replan_state)),
            "terminal": self.terminal,
            "next_cycle_allowed": self.next_cycle_allowed,
            "reason": self.reason,
            "execution_path": {
                "contract_only": True,
                "executes_tasks": False,
                "creates_continuation": False,
                "creates_replan": False,
                "persists_records": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


def build_adaptive_loop_contract(cycle: Mapping[str, Any]) -> dict[str, Any]:
    return AdaptiveLoopContract.from_cycle(cycle).to_dict()


__all__ = ["ADAPTIVE_LOOP_CONTRACT_SCHEMA", "AdaptiveLoopContract", "build_adaptive_loop_contract"]
