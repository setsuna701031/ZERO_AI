from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.runtime.runtime_incident import RuntimeIncidentLayer
from core.runtime.runtime_replay_engine import (
    RuntimeReplayIntegrityRecord,
    RuntimeReplaySession,
)


RECOVERY_STATUS_RECOVERABLE = "recoverable"
RECOVERY_STATUS_INCIDENT = "incident"
RECOVERY_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class RuntimeReplayRecoveryDecision:
    replay_id: str
    recovery_status: str
    recoverable: bool
    deterministic_verified: bool
    integrity_verified: bool
    incident_required: bool
    repair_candidate: bool
    reason: str
    incident_payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "replay_id": self.replay_id,
            "recovery_status": self.recovery_status,
            "recoverable": self.recoverable,
            "deterministic_verified": self.deterministic_verified,
            "integrity_verified": self.integrity_verified,
            "incident_required": self.incident_required,
            "repair_candidate": self.repair_candidate,
            "reason": self.reason,
            "incident_payload": dict(self.incident_payload),
        }


class RuntimeReplayRecoveryBridge:
    def evaluate_replay(
        self,
        replay: RuntimeReplaySession,
    ) -> RuntimeReplayRecoveryDecision:
        integrity_verified = self._integrity_verified(
            replay.integrity_records
        )

        deterministic_verified = (
            replay.verified
            and replay.continuity_verified
            and not replay.block_recommended
        )

        if deterministic_verified and integrity_verified:
            return RuntimeReplayRecoveryDecision(
                replay_id=replay.replay_id,
                recovery_status=RECOVERY_STATUS_RECOVERABLE,
                recoverable=True,
                deterministic_verified=True,
                integrity_verified=True,
                incident_required=False,
                repair_candidate=False,
                reason="deterministic_replay_verified",
                incident_payload={},
            )

        incident_payload = self._build_incident_payload(
            replay=replay,
            integrity_verified=integrity_verified,
            deterministic_verified=deterministic_verified,
        )

        return RuntimeReplayRecoveryDecision(
            replay_id=replay.replay_id,
            recovery_status=RECOVERY_STATUS_INCIDENT,
            recoverable=False,
            deterministic_verified=deterministic_verified,
            integrity_verified=integrity_verified,
            incident_required=True,
            repair_candidate=True,
            reason=incident_payload["reason"],
            incident_payload=incident_payload,
        )

    def _integrity_verified(
        self,
        integrity_records: list[RuntimeReplayIntegrityRecord],
    ) -> bool:
        if not integrity_records:
            return True

        return all(
            item.integrity_verified
            for item in integrity_records
        )

    def _build_incident_payload(
        self,
        replay: RuntimeReplaySession,
        *,
        integrity_verified: bool,
        deterministic_verified: bool,
    ) -> dict[str, Any]:
        layer = RuntimeIncidentLayer()

        if not deterministic_verified:
            layer.attach_event(
                {
                    "incident_id": replay.replay_id,
                    "event_type": "failure",
                    "runtime_phase": "runtime_replay",
                    "reason": "deterministic_replay_failed",
                    "continuity_break": replay.continuity_break,
                    "canonical_status": replay.canonical_status,
                }
            )

        if not integrity_verified:
            layer.attach_event(
                {
                    "incident_id": replay.replay_id,
                    "event_type": "failure",
                    "runtime_phase": "runtime_replay_integrity",
                    "reason": "integrity_verification_failed",
                    "integrity_records": [
                        {
                            "original_execution_id": item.original_execution_id,
                            "replay_execution_id": item.replay_execution_id,
                            "integrity_verified": item.integrity_verified,
                            "mismatch_reason": item.mismatch_reason,
                        }
                        for item in replay.integrity_records
                    ],
                }
            )

        summary = layer.incident_summary()

        reason = "runtime_replay_incident"

        if not deterministic_verified:
            reason = "deterministic_replay_failed"

        if not integrity_verified:
            reason = "integrity_verification_failed"

        return {
            "runtime_phase": "runtime_replay_recovery_bridge",
            "replay_id": replay.replay_id,
            "reason": reason,
            "incident_summary": summary,
            "repair_candidate": {
                "candidate_type": "runtime_repair_candidate",
                "source_replay_id": replay.replay_id,
                "requires_review": replay.review_required,
                "block_recommended": replay.block_recommended,
            },
        }