from __future__ import annotations

"""Passive replan bookkeeping for adaptive engineering loops."""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping


REPLAN_RUNTIME_SCHEMA = "zero.replan_runtime.v2"
_REPLAN_MUTATION_AUTHORITY = object()


def _limit(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return max(0, int(default))


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _identity_from_lineage(lineage: Mapping[str, Any] | None) -> dict[str, str]:
    data = _mapping(lineage)
    goal_id = _text(data.get("goal_id"), _text(data.get("root_goal_id"), "goal"))
    root_goal_id = _text(data.get("root_goal_id"), goal_id)
    session_id = _text(data.get("session_id"), f"goal-session-{root_goal_id}")
    runtime_session_id = _text(data.get("runtime_session_id"), session_id)
    branch_id = _text(data.get("branch_id"), goal_id)
    branch_type = _text(data.get("branch_type"), "root")
    goal_lineage_id = _text(
        data.get("goal_lineage_id"),
        f"{root_goal_id}:{branch_type}:{branch_id}:{session_id}:{runtime_session_id}",
    )
    return {
        "root_goal_id": root_goal_id,
        "source_goal_id": _text(data.get("source_goal_id"), root_goal_id),
        "goal_lineage_id": goal_lineage_id,
        "branch_type": branch_type,
        "branch_id": branch_id,
        "session_id": session_id,
        "runtime_session_id": runtime_session_id,
    }


@dataclass(frozen=True)
class ReplanRuntime:
    """Bounded replan state for one engineering session loop."""

    replan_count: int = 0
    max_replans: int = 1
    last_replan_record: Mapping[str, Any] = field(default_factory=dict)
    root_goal_id: str = ""
    source_goal_id: str = ""
    goal_lineage_id: str = ""
    branch_type: str = "root"
    branch_id: str = ""
    session_id: str = ""
    runtime_session_id: str = ""

    def __post_init__(self) -> None:
        identity = _identity_from_lineage(
            {
                "root_goal_id": self.root_goal_id,
                "source_goal_id": self.source_goal_id,
                "goal_lineage_id": self.goal_lineage_id,
                "branch_type": self.branch_type,
                "branch_id": self.branch_id,
                "session_id": self.session_id,
                "runtime_session_id": self.runtime_session_id,
            }
        )
        object.__setattr__(self, "replan_count", _limit(self.replan_count))
        object.__setattr__(self, "max_replans", _limit(self.max_replans, 1))
        object.__setattr__(self, "last_replan_record", _mapping(self.last_replan_record))
        for key, value in identity.items():
            object.__setattr__(self, key, value)

    @classmethod
    def start(
        cls,
        *,
        replan_count: int = 0,
        max_replans: int = 1,
        goal_lineage: Mapping[str, Any] | None = None,
    ) -> "ReplanRuntime":
        identity = _identity_from_lineage(goal_lineage)
        return cls(replan_count=replan_count, max_replans=max_replans, **identity)

    @property
    def limit_reached(self) -> bool:
        return self.replan_count >= self.max_replans

    def record_replan(self, replan_record: Mapping[str, Any]) -> "ReplanRuntime":
        if self.limit_reached:
            raise RuntimeError("replan_limit_reached")
        return self.replace(
            replan_count=self.replan_count + 1,
            last_replan_record=_mapping(replan_record),
            _authority_token=_REPLAN_MUTATION_AUTHORITY,
        )

    def replace(self, *, _authority_token: object | None = None, **changes: Any) -> "ReplanRuntime":
        if _authority_token is not _REPLAN_MUTATION_AUTHORITY:
            raise PermissionError("replan_mutation_authority_required")
        values = {
            "replan_count": self.replan_count,
            "max_replans": self.max_replans,
            "last_replan_record": copy.deepcopy(dict(self.last_replan_record)),
            "root_goal_id": self.root_goal_id,
            "source_goal_id": self.source_goal_id,
            "goal_lineage_id": self.goal_lineage_id,
            "branch_type": self.branch_type,
            "branch_id": self.branch_id,
            "session_id": self.session_id,
            "runtime_session_id": self.runtime_session_id,
        }
        values.update(changes)
        return ReplanRuntime(**values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REPLAN_RUNTIME_SCHEMA,
            "replan_count": self.replan_count,
            "max_replans": self.max_replans,
            "last_replan_record": copy.deepcopy(dict(self.last_replan_record)),
            "root_goal_id": self.root_goal_id,
            "source_goal_id": self.source_goal_id,
            "goal_lineage_id": self.goal_lineage_id,
            "branch_type": self.branch_type,
            "branch_id": self.branch_id,
            "session_id": self.session_id,
            "runtime_session_id": self.runtime_session_id,
            "limit_reached": self.limit_reached,
            "execution_path": {
                "replan_runtime_bookkeeping_only": True,
                "executes_tasks": False,
                "persists_records": False,
                "mutates_runtime": False,
                "mutates_memory": False,
                "preserves_runtime_identity": True,
            },
        }


__all__ = ["REPLAN_RUNTIME_SCHEMA", "ReplanRuntime"]
