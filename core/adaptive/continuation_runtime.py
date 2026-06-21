from __future__ import annotations

"""Passive continuation bookkeeping for adaptive engineering loops.

ContinuationRuntime is not a RuntimeOrchestrator and does not create goals by
itself. It carries bounded continuation state and immutable runtime identity
between EngineeringGoalLoop and ContinuationCoordinator.
"""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.goals.goal_lineage_contract import (
    create_goal_branch_lineage,
    create_root_goal_lineage,
    extract_goal_lineage,
)

CONTINUATION_RUNTIME_SCHEMA = "zero.continuation_runtime.v2"
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


def _identity_from_lineage(current_goal_id: str, lineage: Mapping[str, Any] | None) -> dict[str, str]:
    data = _mapping(lineage)
    canonical = (
        extract_goal_lineage(data, require_complete=True, reject_conflicts=True)
        if data and data.get("root_goal_id")
        else create_root_goal_lineage(goal_id=current_goal_id)
    )
    return {field: canonical[field] for field in (
        "root_goal_id", "source_goal_id", "goal_lineage_id", "branch_type",
        "branch_id", "session_id", "runtime_session_id",
    )}


@dataclass(frozen=True)
class ContinuationRuntime:
    """Bounded continuation state for one engineering session loop."""

    current_goal_id: str
    continuation_count: int = 0
    max_continuations: int = 1
    last_continuation_goal_id: str = ""
    last_work_item: Mapping[str, Any] = field(default_factory=dict)
    root_goal_id: str = ""
    source_goal_id: str = ""
    goal_lineage_id: str = ""
    branch_type: str = "root"
    branch_id: str = ""
    session_id: str = ""
    runtime_session_id: str = ""

    def __post_init__(self) -> None:
        current = _text(self.current_goal_id, "goal")
        identity = _identity_from_lineage(
            current,
            {
                "root_goal_id": self.root_goal_id,
                "source_goal_id": self.source_goal_id,
                "goal_lineage_id": self.goal_lineage_id,
                "branch_type": self.branch_type,
                "branch_id": self.branch_id,
                "session_id": self.session_id,
                "runtime_session_id": self.runtime_session_id,
                "goal_id": current,
            },
        )
        object.__setattr__(self, "current_goal_id", current)
        object.__setattr__(self, "continuation_count", _limit(self.continuation_count))
        object.__setattr__(self, "max_continuations", _limit(self.max_continuations, 1))
        object.__setattr__(self, "last_continuation_goal_id", _text(self.last_continuation_goal_id))
        object.__setattr__(self, "last_work_item", _mapping(self.last_work_item))
        for key, value in identity.items():
            object.__setattr__(self, key, value)

    @classmethod
    def start(
        cls,
        current_goal_id: str,
        *,
        continuation_count: int = 0,
        max_continuations: int = 1,
        goal_lineage: Mapping[str, Any] | None = None,
    ) -> "ContinuationRuntime":
        identity = _identity_from_lineage(current_goal_id, goal_lineage)
        return cls(
            current_goal_id=current_goal_id,
            continuation_count=continuation_count,
            max_continuations=max_continuations,
            **identity,
        )

    @property
    def limit_reached(self) -> bool:
        return self.continuation_count >= self.max_continuations

    def record_work_item(self, work_item: Mapping[str, Any]) -> "ContinuationRuntime":
        if self.limit_reached:
            raise RuntimeError("continuation_limit_reached")
        item = _mapping(work_item)
        goal_id = _text(item.get("goal_id"), self.current_goal_id)
        branch_id = _text(item.get("branch_id") or item.get("continuation_goal_id"), goal_id)
        branch = create_goal_branch_lineage(
            self.to_dict(),
            goal_id=goal_id,
            branch_type="continuation",
            branch_id=branch_id,
        )
        return self.replace(
            current_goal_id=goal_id,
            continuation_count=self.continuation_count + 1,
            last_continuation_goal_id=goal_id,
            last_work_item=item,
            root_goal_id=branch["root_goal_id"],
            source_goal_id=branch["source_goal_id"],
            goal_lineage_id=branch["goal_lineage_id"],
            branch_type=branch["branch_type"],
            branch_id=branch["branch_id"],
            session_id=branch["session_id"],
            runtime_session_id=branch["runtime_session_id"],
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
            "root_goal_id": self.root_goal_id,
            "source_goal_id": self.source_goal_id,
            "goal_lineage_id": self.goal_lineage_id,
            "branch_type": self.branch_type,
            "branch_id": self.branch_id,
            "session_id": self.session_id,
            "runtime_session_id": self.runtime_session_id,
        }
        values.update(changes)
        return ContinuationRuntime(**values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONTINUATION_RUNTIME_SCHEMA,
            "current_goal_id": self.current_goal_id,
            "goal_id": self.current_goal_id,
            "continuation_count": self.continuation_count,
            "max_continuations": self.max_continuations,
            "last_continuation_goal_id": self.last_continuation_goal_id,
            "last_work_item": copy.deepcopy(dict(self.last_work_item)),
            "root_goal_id": self.root_goal_id,
            "source_goal_id": self.source_goal_id,
            "goal_lineage_id": self.goal_lineage_id,
            "branch_type": self.branch_type,
            "branch_id": self.branch_id,
            "session_id": self.session_id,
            "runtime_session_id": self.runtime_session_id,
            "limit_reached": self.limit_reached,
            "execution_path": {
                "continuation_runtime_bookkeeping_only": True,
                "executes_tasks": False,
                "persists_records": False,
                "mutates_runtime": False,
                "mutates_memory": False,
                "preserves_runtime_identity": True,
            },
        }


__all__ = ["CONTINUATION_RUNTIME_SCHEMA", "ContinuationRuntime"]
