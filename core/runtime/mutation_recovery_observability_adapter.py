from __future__ import annotations

import copy
import json
from typing import Any

from core.runtime.mutation_runtime_pipeline import (
    MutationRuntimePipelineResult,
)
from core.runtime.runtime_recovery_operator_summary import (
    build_runtime_recovery_operator_summary,
)


class MutationRecoveryObservabilityAdapter:
    SCHEMA = "zero.mutation.recovery_observability_adapter.v1"

    def build(
        self,
        result: MutationRuntimePipelineResult,
    ) -> dict[str, Any]:
        if not isinstance(result, MutationRuntimePipelineResult):
            raise TypeError(
                "result must be MutationRuntimePipelineResult"
            )

        verification = result.verification.to_dict()
        approval = result.approval.to_dict()
        apply_result = (
            result.apply_result.to_dict()
            if result.apply_result
            else {}
        )

        blocked_reasons: list[str] = []

        verification_passed = (
            verification.get("verified") is True
            or str(verification.get("status") or "").strip() == "passed"
        )
        approval_passed = (
            approval.get("approved") is True
            or str(approval.get("status") or "").strip() == "approved"
        )
        apply_passed = (
            not apply_result
            or apply_result.get("applied") is True
            or result.dry_run
        )

        if not verification_passed:
            blocked_reasons.append("verification_failed")

        if not approval_passed:
            blocked_reasons.append("approval_failed")

        if not apply_passed:
            blocked_reasons.append("apply_failed")

        if result.dry_run:
            blocked_reasons.append("dry_run_only")

        operator_summary = build_runtime_recovery_operator_summary(
            {
                "ok": result.completed and not blocked_reasons,
                "blocked": bool(blocked_reasons),
                "blockers": blocked_reasons,
                "reports": {
                    "verification": verification,
                    "approval": approval,
                    "apply_result": apply_result,
                },
            }
        )

        payload = {
            "schema": self.SCHEMA,
            "session_id": result.session_id,
            "completed": result.completed,
            "dry_run": result.dry_run,
            "artifact_paths": copy.deepcopy(result.artifact_paths),
            "operator_summary": operator_summary,
        }

        return self._json_safe(payload)

    def _json_safe(self, payload: Any) -> dict[str, Any]:
        encoded = json.dumps(
            payload,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return json.loads(encoded)


def build_mutation_recovery_observability(
    result: MutationRuntimePipelineResult,
) -> dict[str, Any]:
    return MutationRecoveryObservabilityAdapter().build(result)


__all__ = [
    "MutationRecoveryObservabilityAdapter",
    "build_mutation_recovery_observability",
]
