from __future__ import annotations

"""Coordinator for engineering session progression inside EngineeringGoalLoop.

SessionProgressionCoordinator owns passive per-cycle wiring that used to sit in
EngineeringGoalLoop: adaptive-loop controls, lifecycle state, session state,
program state, and loop-decision classification. It does not execute runtime
work, create continuation or replan records, persist evidence, mutate goals, or
write memory.
"""

import copy
from pathlib import Path
from typing import Any, Mapping

from core.session.engineering_session_runtime import EngineeringSessionRuntime
from core.tasks.adaptive_loop_coordinator import AdaptiveLoopCoordinator
from core.tasks.goal_loop_coordinator import GoalLoopCoordinator
from core.tasks.lifecycle_coordinator import LifecycleCoordinator
from core.session.session_coordinator import SessionCoordinator
from core.program.program_coordinator import ProgramCoordinator
from core.goals.goal_lineage_contract import extract_goal_lineage


SESSION_PROGRESSION_COORDINATOR_SCHEMA = "zero.session_progression_coordinator.v1"


def _mapping(value: Any) -> dict[str, Any]:
    # This coordinator enriches the same internal cycle.  A shallow shell avoids
    # repeatedly cloning its complete execution-result graph.
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


class SessionProgressionCoordinator:
    """Attach passive session-cycle controls without owning persistence."""

    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        adaptive_loop_coordinator: AdaptiveLoopCoordinator | Any | None = None,
        lifecycle_coordinator: LifecycleCoordinator | Any | None = None,
        session_coordinator: SessionCoordinator | Any | None = None,
        program_coordinator: ProgramCoordinator | Any | None = None,
        goal_loop_coordinator: GoalLoopCoordinator | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else None
        self.adaptive_loop_coordinator = adaptive_loop_coordinator or AdaptiveLoopCoordinator(repo_root=self.repo_root)
        self.lifecycle_coordinator = lifecycle_coordinator or LifecycleCoordinator(repo_root=self.repo_root)
        self.session_coordinator = session_coordinator or SessionCoordinator(repo_root=self.repo_root)
        self.program_coordinator = program_coordinator or ProgramCoordinator(repo_root=self.repo_root)
        self.goal_loop_coordinator = goal_loop_coordinator or GoalLoopCoordinator()

    def start_runtime(
        self,
        goal_id: str,
        *,
        max_cycles: int = 3,
        max_replans: int = 1,
        max_continuations: int | None = None,
    ) -> EngineeringSessionRuntime:
        return EngineeringSessionRuntime.start(
            goal_id,
            max_cycles=max_cycles,
            max_replans=max_replans,
            max_continuations=max_continuations,
        )

    def attach_cycle_progression(
        self,
        cycle: Mapping[str, Any],
        *,
        runtime: EngineeringSessionRuntime,
        cycle_index: int,
    ) -> tuple[dict[str, Any], EngineeringSessionRuntime]:
        """Attach passive controls to one cycle and return updated runtime."""

        updated = _mapping(cycle)
        lineage = extract_goal_lineage(updated)
        if lineage:
            updated["goal_lineage"] = lineage
        updated = self.adaptive_loop_coordinator.attach_cycle_controls(
            updated,
            previous_observation=runtime.previous_observation,
            replan_count=runtime.replan_count,
            continuation_count=runtime.continuation_count,
            max_replans=runtime.max_replans,
            max_continuations=runtime.max_continuations,
        )
        lifecycle_from_state = "created" if int(cycle_index or 0) == 0 else "running"
        updated = self.lifecycle_coordinator.attach_lifecycle(updated, from_state=lifecycle_from_state)
        updated = self.session_coordinator.attach_session(updated, from_state=runtime.session_from_state)
        next_session_state = _text(
            _mapping(updated.get("engineering_session_state")).get("session_state"),
            runtime.session_from_state,
        )
        updated = self.program_coordinator.attach_program(updated, from_state=runtime.program_from_state)
        next_program_state = _text(
            _mapping(updated.get("engineering_program_state")).get("program_state"),
            runtime.program_from_state,
        )
        state_record = _mapping(updated.get("adaptive_replan_state"))
        loop_decision = self.goal_loop_coordinator.classify_state(state_record).to_dict()
        updated["goal_loop_decision"] = loop_decision
        updated["session_progression_coordinator"] = {
            "schema": SESSION_PROGRESSION_COORDINATOR_SCHEMA,
            "attached_adaptive_loop": True,
            "attached_lifecycle": True,
            "attached_session": True,
            "attached_program": True,
            "attached_goal_loop_decision": True,
            "cycle_index": int(cycle_index or 0),
            "goal_lineage": copy.deepcopy(lineage),
            "execution_path": {
                "coordinator_only": True,
                "executes_tasks": False,
                "creates_continuation": False,
                "creates_replan": False,
                "persists_records": False,
                "mutates_goal_repository": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }
        next_runtime = runtime.append_cycle(updated).replace(
            previous_observation=_mapping(updated.get("adaptive_observation")),
            session_from_state=next_session_state,
            program_from_state=next_program_state,
        )
        return updated, next_runtime

    @staticmethod
    def is_replan_decision(loop_decision: Mapping[str, Any]) -> bool:
        return _mapping(loop_decision).get("action") == "create_replan_record"

    @staticmethod
    def is_continuation_decision(loop_decision: Mapping[str, Any]) -> bool:
        return _mapping(loop_decision).get("action") == "create_continuation"

    @staticmethod
    def is_terminal_decision(loop_decision: Mapping[str, Any]) -> bool:
        return not (
            SessionProgressionCoordinator.is_replan_decision(loop_decision)
            or SessionProgressionCoordinator.is_continuation_decision(loop_decision)
        )


__all__ = ["SESSION_PROGRESSION_COORDINATOR_SCHEMA", "SessionProgressionCoordinator"]
