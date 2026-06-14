from __future__ import annotations

"""Coordinator for program state integration.

ProgramCoordinator attaches passive program state after engineering session is
available.  It also owns Program-level multi-session aggregation semantics:
multiple EngineeringSession state records may be summarized into one Program
state without executing runtime work, persisting records, mutating goals, or
writing memory.
"""

import copy
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.program.engineering_program_state_machine import EngineeringProgramStateMachine
from core.program.engineering_program_transition import EngineeringProgramTransition
from core.goals.goal_completion_authority import is_accepted_goal_completion_result


PROGRAM_COORDINATOR_SCHEMA = "zero.program_coordinator.v1"
PROGRAM_SESSION_AGGREGATION_SCHEMA = "zero.program.session_aggregation.v1"


_PROGRAM_STATES = frozenset({"created", "active", "paused", "blocked", "completed", "failed", "archived"})
_SESSION_STATE_ALIASES = {
    "created": "created",
    "active": "active",
    "running": "active",
    "continuing": "active",
    "replanning": "active",
    "waiting_user": "active",
    "waiting_evidence": "active",
    "paused": "paused",
    "blocked": "blocked",
    "completed": "completed",
    "failed": "failed",
    "archived": "archived",
}


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _state_from_record(value: Any) -> str:
    record = _mapping(value)
    raw = _text(
        record.get("session_state")
        or record.get("program_state")
        or record.get("lifecycle_state")
        or record.get("to_state")
        or record.get("state"),
        "active",
    ).lower()
    return _SESSION_STATE_ALIASES.get(raw, "active")


class ProgramCoordinator:
    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        engineering_program_state_machine: EngineeringProgramStateMachine | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else None
        self.engineering_program_state_machine = engineering_program_state_machine or EngineeringProgramStateMachine()

    def attach_program(self, cycle: Mapping[str, Any], *, from_state: str = "created") -> dict[str, Any]:
        """Attach a single-session program state to one engineering cycle.

        This preserves the existing GoalLoop integration path.  It is a passive
        handoff to EngineeringProgramStateMachine and does not own Program
        aggregation across multiple sessions.
        """

        updated = _mapping(cycle)
        result = self.engineering_program_state_machine.evaluate_cycle(
            updated,
            from_state=_text(from_state, "created"),
        )
        updated["engineering_program_state"] = result.to_dict() if hasattr(result, "to_dict") else _mapping(result)
        updated["program_coordinator"] = {
            "schema": PROGRAM_COORDINATOR_SCHEMA,
            "attached_engineering_program_state": True,
            "from_state": _text(from_state, "created"),
            "multi_session_aggregation": False,
            "execution_path": self._execution_path(),
        }
        return updated

    def aggregate_sessions(
        self,
        session_states: Sequence[Mapping[str, Any]] | Any,
        *,
        goal_id: str = "",
        completion_attestation: Any = None,
    ) -> dict[str, Any]:
        """Return one passive Program summary from many session records.

        Priority is intentionally conservative:
        failed > blocked > active > paused > completed > archived > created.
        A single blocked session keeps the Program blocked because it needs
        operator/planner attention; completed only wins when all sessions are
        completed or archived and at least one session completed.
        """

        sessions = [_mapping(item) for item in _sequence(session_states) if isinstance(item, Mapping)]
        states = [_state_from_record(item) for item in sessions]
        counts = {state: states.count(state) for state in sorted(_PROGRAM_STATES)}
        if not states:
            program_state, reason = "created", "program_has_no_sessions"
        elif counts["failed"]:
            program_state, reason = "failed", "one_or_more_sessions_failed"
        elif counts["blocked"]:
            program_state, reason = "blocked", "one_or_more_sessions_blocked"
        elif counts["active"]:
            program_state, reason = "active", "one_or_more_sessions_active"
        elif counts["paused"]:
            program_state, reason = "paused", "one_or_more_sessions_paused"
        elif counts["completed"] and is_accepted_goal_completion_result(completion_attestation, goal_id=_text(goal_id)):
            program_state, reason = "completed", "all_sessions_completed_or_archived"
        elif counts["completed"]:
            program_state, reason = "active", "canonical_completion_attestation_required"
        elif counts["archived"] == len(states):
            program_state, reason = "archived", "all_sessions_archived"
        else:
            program_state, reason = "created", "sessions_not_started"

        return {
            "schema": PROGRAM_SESSION_AGGREGATION_SCHEMA,
            "program_state": program_state,
            "session_count": len(sessions),
            "session_state_counts": counts,
            "session_states": copy.deepcopy(sessions),
            "terminal": program_state in {"completed", "failed", "archived"},
            "reason": reason,
            "execution_path": {
                "aggregation_only": True,
                "executes_tasks": False,
                "persists_records": False,
                "mutates_goal_repository": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }

    def attach_program_from_sessions(
        self,
        cycle: Mapping[str, Any],
        *,
        session_states: Sequence[Mapping[str, Any]] | Any,
        from_state: str = "created",
    ) -> dict[str, Any]:
        """Attach Program state using multi-session aggregation semantics."""

        updated = _mapping(cycle)
        goal_id = _text(updated.get("goal_id"))
        completion_attestation = updated.get("goal_completion_attestation")
        summary = self.aggregate_sessions(
            session_states,
            goal_id=goal_id,
            completion_attestation=completion_attestation,
        )
        transition = EngineeringProgramTransition(
            from_state=_text(from_state, "created"),
            to_state=_text(summary.get("program_state"), "active"),
            action=_text(summary.get("program_state"), "active"),
            reason=_text(summary.get("reason"), "program_session_aggregation"),
            session_state=summary,
            cycle=updated,
            goal_id=goal_id,
            completion_attestation=completion_attestation,
        )
        result = self.engineering_program_state_machine.transition(transition)
        updated["engineering_program_session_summary"] = copy.deepcopy(summary)
        updated["engineering_program_state"] = result.to_dict() if hasattr(result, "to_dict") else _mapping(result)
        updated["program_coordinator"] = {
            "schema": PROGRAM_COORDINATOR_SCHEMA,
            "attached_engineering_program_state": True,
            "from_state": _text(from_state, "created"),
            "multi_session_aggregation": True,
            "session_count": int(summary.get("session_count") or 0),
            "execution_path": self._execution_path(),
        }
        return updated

    @staticmethod
    def _execution_path() -> dict[str, bool]:
        return {
            "coordinator_only": True,
            "executes_tasks": False,
            "persists_records": False,
            "mutates_goal_repository": False,
            "mutates_runtime": False,
            "mutates_memory": False,
        }


__all__ = [
    "PROGRAM_COORDINATOR_SCHEMA",
    "PROGRAM_SESSION_AGGREGATION_SCHEMA",
    "ProgramCoordinator",
]
