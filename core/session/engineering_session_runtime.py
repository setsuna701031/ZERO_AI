from __future__ import annotations

"""Passive runtime state for engineering session progression.

EngineeringSessionRuntime is not the RuntimeOrchestrator. It is a small
session-loop bookkeeping contract used by SessionProgressionCoordinator to carry
cycle counters and mirrored current state between EngineeringGoalLoop iterations.

Authority boundary:
- ContinuationRuntime owns current_goal_id and continuation_count.
- ReplanRuntime owns replan_count.
- EngineeringSessionRuntime may mirror those values, but it must not become
  their independent owner.

It does not execute tasks, create goals, persist records, mutate runtime, or
write memory.
"""

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Mapping


ENGINEERING_SESSION_RUNTIME_SCHEMA = "zero.engineering_session_runtime.v1"
_CONTINUATION_GOAL_ID_RE = re.compile(r"__continuation_(\d+)(?:_\d+)?$")


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _limit(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return max(0, int(default))


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _continuation_count_from_goal_id(goal_id: Any) -> int | None:
    """Infer a continuation mirror count from canonical continuation goal ids.

    This is only a mirror fallback for legacy callers that update
    current_goal_id directly.  The authoritative writer remains
    ContinuationRuntime.
    """

    text = _text(goal_id)
    match = _CONTINUATION_GOAL_ID_RE.search(text)
    if not match:
        return None
    return _limit(match.group(1))


@dataclass(frozen=True)
class EngineeringSessionRuntime:
    """Bounded session-loop bookkeeping for one engineering goal run.

    The session runtime is mirror-only for continuation/replan-owned fields.
    Prefer mirror_continuation_runtime() and mirror_replan_runtime() over direct
    replace() calls when syncing authoritative runtime state.
    """

    target_goal_id: str
    current_goal_id: str = ""
    cycle_limit: int = 1
    max_replans: int = 1
    max_continuations: int = 1
    replan_count: int = 0
    continuation_count: int = 0
    terminal: bool = False
    stop_reason: str = "max_cycles_reached"
    refusal_reason: str = ""
    session_from_state: str = "created"
    program_from_state: str = "created"
    previous_observation: Mapping[str, Any] | None = None
    cycles: list[Mapping[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        target = _text(self.target_goal_id, "goal")
        current = _text(self.current_goal_id, target)
        object.__setattr__(self, "target_goal_id", target)
        object.__setattr__(self, "current_goal_id", current)
        object.__setattr__(self, "cycle_limit", max(1, _limit(self.cycle_limit, 1)))
        object.__setattr__(self, "max_replans", _limit(self.max_replans, 1))
        object.__setattr__(self, "max_continuations", _limit(self.max_continuations, self.cycle_limit))
        object.__setattr__(self, "replan_count", _limit(self.replan_count))
        object.__setattr__(self, "continuation_count", _limit(self.continuation_count))
        object.__setattr__(self, "terminal", bool(self.terminal))
        object.__setattr__(self, "stop_reason", _text(self.stop_reason, "max_cycles_reached"))
        object.__setattr__(self, "refusal_reason", _text(self.refusal_reason))
        object.__setattr__(self, "session_from_state", _text(self.session_from_state, "created"))
        object.__setattr__(self, "program_from_state", _text(self.program_from_state, "created"))
        object.__setattr__(self, "previous_observation", _mapping(self.previous_observation))
        object.__setattr__(
            self,
            "cycles",
            [copy.deepcopy(dict(cycle)) for cycle in self.cycles if isinstance(cycle, Mapping)],
        )

    @classmethod
    def start(
        cls,
        goal_id: str,
        *,
        max_cycles: int = 3,
        max_replans: int = 1,
        max_continuations: int | None = None,
    ) -> "EngineeringSessionRuntime":
        cycle_limit = max(1, _limit(max_cycles, 1))
        continuation_limit = cycle_limit if max_continuations is None else _limit(max_continuations, cycle_limit)
        return cls(
            target_goal_id=goal_id,
            current_goal_id=goal_id,
            cycle_limit=cycle_limit,
            max_replans=max_replans,
            max_continuations=continuation_limit,
        )

    def append_cycle(self, cycle: Mapping[str, Any]) -> "EngineeringSessionRuntime":
        cycles = [copy.deepcopy(dict(item)) for item in self.cycles]
        cycles.append(copy.deepcopy(dict(cycle)))
        return self.replace(cycles=cycles)

    def mirror_continuation_runtime(self, continuation_runtime: Any) -> "EngineeringSessionRuntime":
        """Mirror current_goal_id and continuation_count from ContinuationRuntime.

        These fields share one authority domain and must be mirrored together.
        """

        return self.replace(
            current_goal_id=getattr(continuation_runtime, "current_goal_id", self.current_goal_id),
            continuation_count=getattr(continuation_runtime, "continuation_count", self.continuation_count),
        )

    def mirror_replan_runtime(self, replan_runtime: Any) -> "EngineeringSessionRuntime":
        """Mirror replan_count from ReplanRuntime."""

        return self.replace(replan_count=getattr(replan_runtime, "replan_count", self.replan_count))

    def replace(self, **changes: Any) -> "EngineeringSessionRuntime":
        values = {
            "target_goal_id": self.target_goal_id,
            "current_goal_id": self.current_goal_id,
            "cycle_limit": self.cycle_limit,
            "max_replans": self.max_replans,
            "max_continuations": self.max_continuations,
            "replan_count": self.replan_count,
            "continuation_count": self.continuation_count,
            "terminal": self.terminal,
            "stop_reason": self.stop_reason,
            "refusal_reason": self.refusal_reason,
            "session_from_state": self.session_from_state,
            "program_from_state": self.program_from_state,
            "previous_observation": copy.deepcopy(dict(self.previous_observation or {})),
            "cycles": [copy.deepcopy(dict(cycle)) for cycle in self.cycles],
        }

        # Backward-compatible drift protection: legacy callers may only mirror
        # current_goal_id from ContinuationRuntime.  Because current_goal_id and
        # continuation_count share the same authority domain, infer the mirrored
        # continuation count from canonical continuation goal ids when the count
        # is not supplied explicitly.
        if "current_goal_id" in changes and "continuation_count" not in changes:
            inferred_count = _continuation_count_from_goal_id(changes.get("current_goal_id"))
            if inferred_count is not None:
                changes["continuation_count"] = max(self.continuation_count, inferred_count)

        values.update(changes)
        return EngineeringSessionRuntime(**values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_SESSION_RUNTIME_SCHEMA,
            "target_goal_id": self.target_goal_id,
            "current_goal_id": self.current_goal_id,
            "cycle_limit": self.cycle_limit,
            "max_replans": self.max_replans,
            "max_continuations": self.max_continuations,
            "replan_count": self.replan_count,
            "continuation_count": self.continuation_count,
            "terminal": self.terminal,
            "stop_reason": self.stop_reason,
            "refusal_reason": self.refusal_reason,
            "session_from_state": self.session_from_state,
            "program_from_state": self.program_from_state,
            "previous_observation": copy.deepcopy(dict(self.previous_observation or {})),
            "cycles": [copy.deepcopy(dict(cycle)) for cycle in self.cycles],
            "authority": {
                "current_goal_id": "ContinuationRuntime",
                "continuation_count": "ContinuationRuntime",
                "replan_count": "ReplanRuntime",
                "session_runtime_role": "mirror_only",
            },
            "execution_path": {
                "session_runtime_bookkeeping_only": True,
                "mirrors_continuation_runtime": True,
                "mirrors_replan_runtime": True,
                "owns_current_goal_id": False,
                "owns_continuation_count": False,
                "owns_replan_count": False,
                "executes_tasks": False,
                "creates_continuation": False,
                "creates_replan": False,
                "persists_records": False,
                "mutates_goal_repository": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


__all__ = ["ENGINEERING_SESSION_RUNTIME_SCHEMA", "EngineeringSessionRuntime"]
