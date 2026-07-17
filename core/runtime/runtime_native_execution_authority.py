from __future__ import annotations

import copy
from typing import Any

from core.runtime.runtime_execution_authority_policy import CANONICAL_EXECUTION_AUTHORITY_MATRIX


RUNTIME_NATIVE_AUTHORITY_PATH = [
    "runtime_native_scheduler/runtime_native_execution_dispatch/runtime_native_multisession_coordination",
    "runtime_native_mainline",
    "runtime_native_agent_loop.run_goal",
    "TaskRunner",
    "StepExecutor",
]


def runtime_native_execution_path(
    *,
    entrypoint: str,
    delegation_only: bool,
) -> dict[str, Any]:
    """Describe the sealed runtime-native execution ownership contract."""
    return {
        "entrypoint": str(entrypoint or ""),
        "authority_path": copy.deepcopy(RUNTIME_NATIVE_AUTHORITY_PATH),
        "delegation_only": bool(delegation_only),
        "direct_execution": False,
        "runtime_owns_execution": True,
        "taskrunner_required": True,
        "step_executor_endpoint_only": True,
        "canonical_execution_authority_matrix": copy.deepcopy(CANONICAL_EXECUTION_AUTHORITY_MATRIX),
        "execution_authority_gate_required": True,
        "runtime_capability_validation_required": True,
    }


__all__ = [
    "RUNTIME_NATIVE_AUTHORITY_PATH",
    "runtime_native_execution_path",
]
