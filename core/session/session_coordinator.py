from __future__ import annotations

"""Coordinator for session state integration.

SessionCoordinator attaches passive session state after engineering lifecycle is
available. It does not execute runtime work, persist records, mutate goals, or
write memory.
"""

import copy
from pathlib import Path
from typing import Any, Mapping

from core.session.engineering_session_state_machine import EngineeringSessionStateMachine


SESSION_COORDINATOR_SCHEMA = "zero.session_coordinator.v1"


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


class SessionCoordinator:
    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        engineering_session_state_machine: EngineeringSessionStateMachine | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else None
        self.engineering_session_state_machine = engineering_session_state_machine or EngineeringSessionStateMachine()

    def attach_session(self, cycle: Mapping[str, Any], *, from_state: str = "created") -> dict[str, Any]:
        updated = _mapping(cycle)
        result = self.engineering_session_state_machine.evaluate_cycle(
            updated,
            from_state=_text(from_state, "created"),
        )
        updated["engineering_session_state"] = result.to_dict() if hasattr(result, "to_dict") else _mapping(result)
        updated["session_coordinator"] = {
            "schema": SESSION_COORDINATOR_SCHEMA,
            "attached_engineering_session_state": True,
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


__all__ = ["SESSION_COORDINATOR_SCHEMA", "SessionCoordinator"]
