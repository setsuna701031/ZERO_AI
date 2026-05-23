from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


REPLAY_RECOVERY_SEAL_RECOVERABLE = "sealed_recoverable"
REPLAY_RECOVERY_SEAL_REVIEW_REQUIRED = "sealed_review_required"
REPLAY_RECOVERY_SEAL_FAILED = "sealed_failed"


@dataclass(frozen=True)
class RuntimeReplayRecoverySeal:
    seal_id: str
    replay_id: str
    recovery_id: str
    execution_id: str
    seal_status: str
    recoverable: bool
    review_required: bool
    failed: bool
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seal_id": self.seal_id,
            "replay_id": self.replay_id,
            "recovery_id": self.recovery_id,
            "execution_id": self.execution_id,
            "seal_status": self.seal_status,
            "recoverable": self.recoverable,
            "review_required": self.review_required,
            "failed": self.failed,
            "reason": self.reason,
            "evidence": dict(self.evidence),
        }


class RuntimeReplayRecoverySealBuilder:
    def build_seal(
        self,
        execution_result: Any,
    ) -> RuntimeReplayRecoverySeal:
        payload = (
            execution_result.to_dict()
            if hasattr(execution_result, "to_dict")
            else dict(execution_result)
        )

        execution_id = str(payload.get("execution_id") or "")
        recovery_id = str(payload.get("recovery_id") or "")
        replay_id = self._extract_replay_id(payload, recovery_id)

        status = str(payload.get("status") or "").lower()
        chain_status = str(payload.get("recovery_chain_status") or "").lower()
        continuation = str(payload.get("continuation_decision") or "").lower()

        failed = status in {"failed", "blocked"}

        verified_completed = (
            status == "completed"
            and chain_status == "verified"
        )

        review_required = (
            not verified_completed
            and (
                chain_status == "review_required"
                or continuation in {"requires_review", "review_required"}
                or status == "review_required"
            )
        )

        if failed:
            seal_status = REPLAY_RECOVERY_SEAL_FAILED
            reason = "recovery_execution_failed"
            recoverable = False
            review_required = False
        elif verified_completed:
            seal_status = REPLAY_RECOVERY_SEAL_RECOVERABLE
            reason = "recovery_execution_sealed_recoverable"
            recoverable = True
            review_required = False
        elif review_required:
            seal_status = REPLAY_RECOVERY_SEAL_REVIEW_REQUIRED
            reason = "recovery_execution_requires_review"
            recoverable = False
        else:
            seal_status = REPLAY_RECOVERY_SEAL_RECOVERABLE
            reason = "recovery_execution_sealed_recoverable"
            recoverable = True

        return RuntimeReplayRecoverySeal(
            seal_id=f"seal::{replay_id or recovery_id or execution_id}",
            replay_id=replay_id,
            recovery_id=recovery_id,
            execution_id=execution_id,
            seal_status=seal_status,
            recoverable=recoverable,
            review_required=review_required,
            failed=failed,
            reason=reason,
            evidence={
                "execution_status": status,
                "recovery_chain_status": chain_status,
                "continuation_decision": continuation,
                "action_count": len(payload.get("action_results") or []),
                "source": "runtime_replay_recovery_seal",
            },
        )

    def _extract_replay_id(
        self,
        payload: dict[str, Any],
        recovery_id: str,
    ) -> str:
        source_session_id = str(payload.get("source_session_id") or "")
        if source_session_id:
            return source_session_id

        if recovery_id.startswith("recovery::"):
            return recovery_id.split("recovery::", 1)[1]

        return ""