from __future__ import annotations

from core.runtime.runtime_evidence_replay_validation import RuntimeEvidenceReplayValidator
from core.runtime.runtime_mainline_evidence_seal import build_runtime_mainline_evidence_seal
from core.runtime.runtime_recovery_evidence_replay_validation_attachment import (
    RuntimeRecoveryEvidenceReplayValidationAttachment,
    attach_recovery_evidence_to_replay_validation,
)


def test_attach_recovery_evidence_to_replay_validation_report() -> None:
    report = RuntimeEvidenceReplayValidator().validate(
        build_runtime_mainline_evidence_seal(
            workspace_root="workspace",
            seal_id="recovery-validation-attachment",
        )
    )

    attachment = attach_recovery_evidence_to_replay_validation(
        validation_report=report,
        evidence_attachment={
            "schema": "zero.runtime.recovery_evidence_attachment.v1",
            "bundle_id": "bundle-1",
            "recovery_artifact": {
                "readiness": "ready",
                "status": "ready",
            },
        },
    )

    assert attachment["schema"] == RuntimeRecoveryEvidenceReplayValidationAttachment.SCHEMA
    assert attachment["validation_ok"] is True
    assert attachment["validation_issue_count"] == 0
    assert attachment["recovery_readiness"] == "ready"
    assert attachment["recovery_status"] == "ready"


def test_attach_recovery_evidence_to_failed_replay_validation_report() -> None:
    report = RuntimeEvidenceReplayValidator().validate(None)

    attachment = attach_recovery_evidence_to_replay_validation(
        validation_report=report,
        evidence_attachment={
            "schema": "zero.runtime.recovery_evidence_attachment.v1",
            "bundle_id": "bundle-1",
            "recovery_artifact": {
                "readiness": "blocked",
                "status": "blocked",
            },
        },
    )

    assert attachment["validation_ok"] is False
    assert attachment["validation_issue_count"] > 0
    assert attachment["recovery_readiness"] == "blocked"
    assert attachment["recovery_status"] == "blocked"
