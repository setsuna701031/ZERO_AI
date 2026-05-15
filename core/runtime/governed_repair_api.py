from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from core.runtime.mutation_runtime_pipeline import MutationRuntimePipelineResult
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationVerificationRequirement,
)
from core.runtime.repair_transaction_execution_bridge import (
    execute_committed_runtime_repair_transaction,
)
from core.tasks.runtime_repair_transaction import (
    commit_runtime_repair_transaction,
    create_runtime_repair_transaction,
    stage_runtime_repair_mutation,
)

GovernedRepairGateHook = Callable[[dict[str, Any]], Any]


def execute_governed_repair_mutation(
    *,
    task_id: Any,
    proposal_id: Any,
    goal: Any,
    mutation: Mapping[str, Any],
    workspace_root: str | Path,
    sandbox_source_root: str | Path,
    rollback_root: str | Path,
    report_root: str | Path,
    allowed_roots: list[str] | tuple[str, ...],
    authorization: Any = None,
    scope_gate: Any = None,
    metadata: Any = None,
    approval_mode: MutationApprovalMode = MutationApprovalMode.REVIEW_REQUIRED,
    verification: MutationVerificationRequirement = MutationVerificationRequirement.TARGETED_TESTS,
    risk_level: MutationRiskLevel = MutationRiskLevel.MEDIUM,
    dry_run: bool | None = None,
    gate_hook: GovernedRepairGateHook | None = None,
    use_runtime_recovery_gate: bool = False,
) -> MutationRuntimePipelineResult:
    """
    Public governed repair API.

    Upper layers should call this instead of directly touching:
    - runtime_repair_transaction lifecycle internals
    - repair transaction execution bridge
    - mutation gateway internals
    - mutation runtime pipeline
    - patch apply primitives

    gate_hook is an optional policy/gate extension point. It is passed through
    to the execution layer without importing recovery-specific gate modules here.
    """

    transaction = create_runtime_repair_transaction(
        task_id=task_id,
        proposal_id=proposal_id,
        goal=goal,
        authorization=authorization,
        scope_gate=scope_gate,
        metadata=metadata,
    )

    staged = stage_runtime_repair_mutation(
        transaction,
        mutation,
    )

    committed = commit_runtime_repair_transaction(
        staged,
    )

    if committed.get("state") != "committed":
        raise ValueError(
            "governed_repair_transaction_not_committed:"
            + str(committed.get("blocked_reason") or committed.get("summary") or "unknown")
        )

    return execute_committed_runtime_repair_transaction(
        committed,
        workspace_root=workspace_root,
        sandbox_source_root=sandbox_source_root,
        rollback_root=rollback_root,
        report_root=report_root,
        allowed_roots=allowed_roots,
        approval_mode=approval_mode,
        verification=verification,
        risk_level=risk_level,
        dry_run=dry_run,
        gate_hook=gate_hook,
        use_runtime_recovery_gate=use_runtime_recovery_gate,
    )
