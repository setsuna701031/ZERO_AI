from __future__ import annotations

"""Passive replan bookkeeping for adaptive engineering loops."""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping


REPLAN_RUNTIME_SCHEMA = "zero.replan_runtime.v1"


def _limit(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return max(0, int(default))


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class ReplanRuntime:
    """Bounded replan state for one engineering session loop."""

    replan_count: int = 0
    max_replans: int = 1
    last_replan_record: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "replan_count", _limit(self.replan_count))
        object.__setattr__(self, "max_replans", _limit(self.max_replans, 1))
        object.__setattr__(self, "last_replan_record", _mapping(self.last_replan_record))

    @classmethod
    def start(cls, *, replan_count: int = 0, max_replans: int = 1) -> "ReplanRuntime":
        return cls(replan_count=replan_count, max_replans=max_replans)

    @property
    def limit_reached(self) -> bool:
        return self.replan_count >= self.max_replans

    def record_replan(self, replan_record: Mapping[str, Any]) -> "ReplanRuntime":
        return self.replace(
            replan_count=self.replan_count + 1,
            last_replan_record=_mapping(replan_record),
        )

    def replace(self, **changes: Any) -> "ReplanRuntime":
        values = {
            "replan_count": self.replan_count,
            "max_replans": self.max_replans,
            "last_replan_record": copy.deepcopy(dict(self.last_replan_record)),
        }
        values.update(changes)
        return ReplanRuntime(**values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REPLAN_RUNTIME_SCHEMA,
            "replan_count": self.replan_count,
            "max_replans": self.max_replans,
            "last_replan_record": copy.deepcopy(dict(self.last_replan_record)),
            "limit_reached": self.limit_reached,
            "execution_path": {
                "replan_runtime_bookkeeping_only": True,
                "executes_tasks": False,
                "persists_records": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


__all__ = ["REPLAN_RUNTIME_SCHEMA", "ReplanRuntime"]
