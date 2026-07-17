from __future__ import annotations

import copy


ADAPTIVE_PLANNING_OWNERSHIP_SCHEMA = "zero.adaptive_planning_ownership.v1"


def adaptive_planning_ownership_contract() -> dict[str, object]:
    return copy.deepcopy(
        {
            "schema": ADAPTIVE_PLANNING_OWNERSHIP_SCHEMA,
            "adaptive_planner_decides_only": True,
            "adaptive_persistence_gateway_persists_only": True,
            "goal_loop_owns_long_horizon_cycles": True,
            "continuation_coordinator_owns_continuation_creation": True,
            "replan_coordinator_owns_replan_creation": True,
            "terminal_coordinator_owns_terminal_result_assembly": True,
            "runtime_execution_owned_here": False,
            "direct_execution": False,
        }
    )


__all__ = ["ADAPTIVE_PLANNING_OWNERSHIP_SCHEMA", "adaptive_planning_ownership_contract"]
