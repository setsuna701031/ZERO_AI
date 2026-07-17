from __future__ import annotations

from typing import Any

from core.runtime.runtime_recovery_executor import (
    RuntimeRecoveryExecutor,
)
from core.runtime.runtime_replay_recovery_plan import (
    RuntimeReplayRecoveryPlan,
)


class RuntimeReplayRecoveryExecutorBridge:
    """
    Bridge:
        RuntimeReplayRecoveryPlan
            ↓
        RuntimeRecoveryExecutor.execute_recovery()
    """

    def __init__(
        self,
        executor: RuntimeRecoveryExecutor | None = None,
    ) -> None:
        self.executor = (
            executor
            if executor is not None
            else RuntimeRecoveryExecutor()
        )

    def execute_plan(
        self,
        plan: RuntimeReplayRecoveryPlan,
        *,
        source_state: dict[str, Any] | None = None,
        approval: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        recovery_chain = self._build_recovery_chain(
            plan=plan,
            metadata=metadata,
        )

        return self.executor.execute_recovery(
            recovery_chain,
            source_state=source_state,
            approval=approval,
            metadata=metadata,
        )

    def _build_recovery_chain(
        self,
        *,
        plan: RuntimeReplayRecoveryPlan,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        verification_result = {
            "recoverable": plan.recoverable,
            "incident_required": plan.incident_required,
            "repair_candidate": plan.repair_candidate,
            "reason": plan.reason,
        }

        recovery_plan = {
            "plan_id": plan.plan_id,
            "steps": [
                {
                    "step_id": step.step_id,
                    "step_type": step.step_type,
                    "status": step.status,
                    "payload": dict(step.payload),
                }
                for step in plan.steps
            ],
        }

        replay_reference = {
            "replay_id": plan.replay_id,
            "reason": plan.reason,
        }

        status = (
            "verified"
            if plan.recoverable
            else "review_required"
        )

        return {
            "recovery_id": f"recovery::{plan.replay_id}",
            "source_session_id": plan.replay_id,
            "status": status,
            "verification_result": verification_result,
            "recovery_plan": recovery_plan,
            "replay_reference": replay_reference,
            "metadata": dict(metadata or {}),
        }