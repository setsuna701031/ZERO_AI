from __future__ import annotations

import pytest

from core.runtime.controlled_mutation_sandbox_executor import (
    ControlledMutationSandboxExecutor,
    ControlledMutationSandboxExecutorRejected,
)
from core.runtime.controlled_mutation_sandbox_plan import (
    ControlledMutationSandboxPlan,
)


def _plan() -> ControlledMutationSandboxPlan:
    plan = ControlledMutationSandboxPlan.plan_workspace_copy(
        sandbox_id="sandbox:allow_path_test",
        mutation_id="mutation:allow_path_test",
        target_paths=[
            "core/runtime/controlled_mutation_sandbox_executor.py",
        ],
        evidence_refs=[
            "runtime_evidence:allow_path_test",
        ],
        metadata={
            "allow_paths": [
                "core/runtime/controlled_mutation_sandbox_executor.py",
            ],
        },
        runtime_args={
            "allow_paths": [
                "core/runtime/controlled_mutation_sandbox_executor.py",
            ],
        },
    )

    plan.plan_patch_apply(
        patch_identity={
            "patch_id": "patch:allow_path_test",
        }
    )

    return plan


def test_controlled_mutation_sandbox_executor_accepts_allowed_target() -> None:
    executor = ControlledMutationSandboxExecutor(
        "sandbox_executor:allow_path_test",
        _plan(),
    )

    record = executor.record_patch_apply(
        target_paths=[
            "core/runtime/controlled_mutation_sandbox_executor.py",
        ],
    )

    assert record.target_paths == [
        "core/runtime/controlled_mutation_sandbox_executor.py",
    ]


def test_controlled_mutation_sandbox_executor_rejects_outside_target() -> None:
    executor = ControlledMutationSandboxExecutor(
        "sandbox_executor:allow_path_test",
        _plan(),
    )

    with pytest.raises(
        ControlledMutationSandboxExecutorRejected
    ):
        executor.record_patch_apply(
            target_paths=[
                "core/runtime/audit_log.py",
            ],
        )