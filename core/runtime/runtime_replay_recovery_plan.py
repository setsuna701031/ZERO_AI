from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.runtime.runtime_replay_recovery_bridge import (
    RuntimeReplayRecoveryDecision,
)


RECOVERY_PLAN_STATUS_READY = "ready"
RECOVERY_PLAN_STATUS_NOT_REQUIRED = "not_required"
RECOVERY_PLAN_STATUS_BLOCKED = "blocked"


@dataclass(frozen=True)
class RuntimeReplayRecoveryPlanStep:
    step_id: str
    step_type: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeReplayRecoveryPlan:
    plan_id: str
    replay_id: str
    status: str
    recoverable: bool
    incident_required: bool
    repair_candidate: bool
    reason: str
    steps: list[RuntimeReplayRecoveryPlanStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "replay_id": self.replay_id,
            "status": self.status,
            "recoverable": self.recoverable,
            "incident_required": self.incident_required,
            "repair_candidate": self.repair_candidate,
            "reason": self.reason,
            "steps": [
                {
                    "step_id": step.step_id,
                    "step_type": step.step_type,
                    "status": step.status,
                    "payload": dict(step.payload),
                }
                for step in self.steps
            ],
            "metadata": dict(self.metadata),
        }


class RuntimeReplayRecoveryPlanBuilder:
    def build_plan(
        self,
        decision: RuntimeReplayRecoveryDecision,
    ) -> RuntimeReplayRecoveryPlan:
        if decision.recoverable:
            return RuntimeReplayRecoveryPlan(
                plan_id=f"recovery-plan::{decision.replay_id}",
                replay_id=decision.replay_id,
                status=RECOVERY_PLAN_STATUS_NOT_REQUIRED,
                recoverable=True,
                incident_required=False,
                repair_candidate=False,
                reason="replay_already_recoverable",
                steps=[],
                metadata={
                    "source": "runtime_replay_recovery_plan",
                },
            )

        steps = [
            RuntimeReplayRecoveryPlanStep(
                step_id=f"{decision.replay_id}::collect_incident",
                step_type="collect_runtime_incident",
                status="ready",
                payload={
                    "incident_payload": dict(decision.incident_payload),
                },
            ),
            RuntimeReplayRecoveryPlanStep(
                step_id=f"{decision.replay_id}::prepare_repair_candidate",
                step_type="prepare_runtime_repair_candidate",
                status="ready",
                payload={
                    "reason": decision.reason,
                    "repair_candidate": decision.repair_candidate,
                },
            ),
            RuntimeReplayRecoveryPlanStep(
                step_id=f"{decision.replay_id}::require_review",
                step_type="require_runtime_recovery_review",
                status="ready",
                payload={
                    "replay_id": decision.replay_id,
                    "incident_required": decision.incident_required,
                },
            ),
        ]

        return RuntimeReplayRecoveryPlan(
            plan_id=f"recovery-plan::{decision.replay_id}",
            replay_id=decision.replay_id,
            status=RECOVERY_PLAN_STATUS_READY,
            recoverable=False,
            incident_required=decision.incident_required,
            repair_candidate=decision.repair_candidate,
            reason=decision.reason,
            steps=steps,
            metadata={
                "source": "runtime_replay_recovery_plan",
            },
        )