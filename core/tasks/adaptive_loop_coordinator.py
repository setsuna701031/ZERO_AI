from __future__ import annotations

"""Coordinator for Adaptive Loop contracts inside EngineeringGoalLoop.

AdaptiveLoopCoordinator owns the passive assembly of adaptive loop artifacts for
one engineering cycle:

Runtime contract / adaptive decision
    -> AdaptiveReplanContract
    -> AdaptiveReplanStateMachine result
    -> AdaptiveObservation
    -> AdaptiveDelta
    -> AdaptiveLoopContract

It does not execute runtime work, create continuation or replan records, persist
records, mutate goals, or write memory.
"""

import copy
from pathlib import Path
from typing import Any, Mapping

from core.adaptive.adaptive_delta import build_adaptive_delta
from core.adaptive.adaptive_loop_contract import build_adaptive_loop_contract
from core.adaptive.adaptive_observation import build_adaptive_observation_from_cycle
from core.adaptive.adaptive_replan_state_machine import AdaptiveReplanStateMachine
from core.tasks.adaptive_replan_contract import build_adaptive_replan_contract


ADAPTIVE_LOOP_COORDINATOR_SCHEMA = "zero.adaptive_loop_coordinator.v1"


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


class AdaptiveLoopCoordinator:
    """Build passive Adaptive Loop v2 records for a cycle."""

    def __init__(
        self,
        *,
        repo_root: str | Path | None = None,
        adaptive_replan_state_machine: AdaptiveReplanStateMachine | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else None
        self.adaptive_replan_state_machine = adaptive_replan_state_machine or AdaptiveReplanStateMachine()

    def attach_cycle_controls(
        self,
        cycle: Mapping[str, Any],
        *,
        previous_observation: Mapping[str, Any] | None = None,
        replan_count: int = 0,
        continuation_count: int = 0,
        max_replans: int = 1,
        max_continuations: int = 3,
    ) -> dict[str, Any]:
        """Return a cycle with passive adaptive-loop records attached."""

        updated = _mapping(cycle)
        contract = build_adaptive_replan_contract(
            cycle=updated,
            replan_count=replan_count,
            continuation_count=continuation_count,
            max_replans=max_replans,
            max_continuations=max_continuations,
        )
        contract_record = contract.to_dict()
        updated["adaptive_replan_contract"] = contract_record

        state_result = self.adaptive_replan_state_machine.evaluate_contract(
            contract_record,
            goal_id=str(updated.get("goal_id") or ""),
            completion_attestation=updated.get("goal_completion_attestation"),
        )
        state_record = state_result.to_dict() if hasattr(state_result, "to_dict") else _mapping(state_result)
        updated["adaptive_replan_state"] = state_record

        updated["adaptive_observation"] = build_adaptive_observation_from_cycle(updated)
        updated["adaptive_delta"] = build_adaptive_delta(previous_observation, updated["adaptive_observation"])
        updated["adaptive_loop_contract"] = build_adaptive_loop_contract(updated)
        updated["adaptive_loop_coordinator"] = {
            "schema": ADAPTIVE_LOOP_COORDINATOR_SCHEMA,
            "attached_replan_contract": True,
            "attached_replan_state": True,
            "attached_observation": True,
            "attached_delta": True,
            "attached_loop_contract": True,
            "execution_path": {
                "coordinator_only": True,
                "executes_tasks": False,
                "creates_continuation": False,
                "creates_replan": False,
                "persists_records": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }
        return updated


__all__ = ["ADAPTIVE_LOOP_COORDINATOR_SCHEMA", "AdaptiveLoopCoordinator"]
