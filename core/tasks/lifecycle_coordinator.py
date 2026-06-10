from __future__ import annotations

"""Coordinator for Engineering Lifecycle state integration.

LifecycleCoordinator attaches lifecycle-state-machine output to an engineering
cycle after Adaptive Loop v2 records are available.  It does not execute runtime
work, persist records, mutate goals, or write memory.
"""

import copy
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_lifecycle_state_machine import EngineeringLifecycleStateMachine


LIFECYCLE_COORDINATOR_SCHEMA = "zero.lifecycle_coordinator.v1"


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


class LifecycleCoordinator:
    """Attach passive engineering lifecycle state to a cycle."""

    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        engineering_lifecycle_state_machine: EngineeringLifecycleStateMachine | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else None
        self.engineering_lifecycle_state_machine = (
            engineering_lifecycle_state_machine or EngineeringLifecycleStateMachine()
        )

    def attach_lifecycle(self, cycle: Mapping[str, Any], *, from_state: str = "created") -> dict[str, Any]:
        updated = _mapping(cycle)
        lifecycle_result = self.engineering_lifecycle_state_machine.evaluate_cycle(
            updated,
            from_state=_text(from_state, "created"),
        )
        updated["engineering_lifecycle_state"] = (
            lifecycle_result.to_dict() if hasattr(lifecycle_result, "to_dict") else _mapping(lifecycle_result)
        )
        updated["lifecycle_coordinator"] = {
            "schema": LIFECYCLE_COORDINATOR_SCHEMA,
            "attached_engineering_lifecycle_state": True,
            "from_state": _text(from_state, "created"),
            "execution_path": {
                "coordinator_only": True,
                "executes_tasks": False,
                "persists_records": False,
                "mutates_goal_repository": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }
        return updated


__all__ = ["LIFECYCLE_COORDINATOR_SCHEMA", "LifecycleCoordinator"]
