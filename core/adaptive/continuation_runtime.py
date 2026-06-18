from __future__ import annotations

"""Passive continuation bookkeeping for adaptive engineering loops.

ContinuationRuntime is not a RuntimeOrchestrator and does not create goals by
itself.  It carries the current goal id, continuation count, and limit between
EngineeringGoalLoop and ContinuationCoordinator.
"""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping


CONTINUATION_RUNTIME_SCHEMA = "zero.continuation_runtime.v1"
_CONTINUATION_MUTATION_AUTHORITY = object()


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


@dataclass(frozen=True)
class ContinuationRuntime:
    """Bounded continuation state for one engineering session loop."""

    current_goal_id: str
    continuation_count: int = 0
    max_continuations: int = 1
    last_continuation_goal_id: str = ""
    last_work_item: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        current = _text(self.current_goal_id, "goal")
        object.__setattr__(self, "current_goal_id", current)
        object.__setattr__(self, "continuation_count", _limit(self.continuation_count))
        object.__setattr__(self, "max_continuations", _limit(self.max_continuations, 1))
        object.__setattr__(self, "last_continuation_goal_id", _text(self.last_continuation_goal_id))
        object.__setattr__(self, "last_work_item", _mapping(self.last_work_item))

    @classmethod
    def start(
        cls,
        current_goal_id: str,
        *,
        continuation_count: int = 0,
        max_continuations: int = 1,
    ) -> "ContinuationRuntime":
        return cls(
            current_goal_id=current_goal_id,
            continuation_count=continuation_count,
            max_continuations=max_continuations,
        )

    @property
    def limit_reached(self) -> bool:
        return self.continuation_count >= self.max_continuations

    def record_work_item(self, work_item: Mapping[str, Any]) -> "ContinuationRuntime":
        if self.limit_reached:
            raise RuntimeError("continuation_limit_reached")
        item = _mapping(work_item)
        goal_id = _text(item.get("goal_id"), self.current_goal_id)
        return self.replace(
            current_goal_id=goal_id,
            continuation_count=self.continuation_count + 1,
            last_continuation_goal_id=goal_id,
            last_work_item=item,
            _authority_token=_CONTINUATION_MUTATION_AUTHORITY,
        )

    def replace(self, *, _authority_token: object | None = None, **changes: Any) -> "ContinuationRuntime":
        if _authority_token is not _CONTINUATION_MUTATION_AUTHORITY:
            raise PermissionError("continuation_mutation_authority_required")
        values = {
            "current_goal_id": self.current_goal_id,
            "continuation_count": self.continuation_count,
            "max_continuations": self.max_continuations,
            "last_continuation_goal_id": self.last_continuation_goal_id,
            "last_work_item": copy.deepcopy(dict(self.last_work_item)),
        }
        values.update(changes)
        return ContinuationRuntime(**values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONTINUATION_RUNTIME_SCHEMA,
            "current_goal_id": self.current_goal_id,
            "continuation_count": self.continuation_count,
            "max_continuations": self.max_continuations,
            "last_continuation_goal_id": self.last_continuation_goal_id,
            "last_work_item": copy.deepcopy(dict(self.last_work_item)),
            "limit_reached": self.limit_reached,
            "execution_path": {
                "continuation_runtime_bookkeeping_only": True,
                "executes_tasks": False,
                "persists_records": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


__all__ = ["CONTINUATION_RUNTIME_SCHEMA", "ContinuationRuntime"]
