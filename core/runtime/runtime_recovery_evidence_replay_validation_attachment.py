from __future__ import annotations

import copy
import json
from typing import Any

from core.runtime.runtime_evidence_replay_validation import (
    RuntimeEvidenceReplayValidationReport,
)
from core.runtime.runtime_recovery_evidence_attachment import (
    attach_runtime_recovery_evidence,
)


class RuntimeRecoveryEvidenceReplayValidationAttachment:
    SCHEMA = "zero.runtime.recovery_evidence_replay_validation_attachment.v1"

    def attach(
        self,
        *,
        validation_report: RuntimeEvidenceReplayValidationReport,
        evidence_attachment: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(validation_report, RuntimeEvidenceReplayValidationReport):
            raise TypeError("validation_report must be RuntimeEvidenceReplayValidationReport")

        attachment = copy.deepcopy(evidence_attachment) if isinstance(evidence_attachment, dict) else {}

        payload = {
            "schema": self.SCHEMA,
            "validation_ok": validation_report.ok,
            "validation_fingerprint": validation_report.fingerprint,
            "validation_issue_count": len(validation_report.issues()),
            "validation_issues": validation_report.issues(),
            "evidence_attachment": attachment,
            "recovery_readiness": str(
                attachment.get("recovery_artifact", {}).get("readiness", "")
                if isinstance(attachment.get("recovery_artifact"), dict)
                else ""
            ),
            "recovery_status": str(
                attachment.get("recovery_artifact", {}).get("status", "")
                if isinstance(attachment.get("recovery_artifact"), dict)
                else ""
            ),
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


def attach_recovery_evidence_to_replay_validation(
    *,
    validation_report: RuntimeEvidenceReplayValidationReport,
    evidence_attachment: dict[str, Any],
) -> dict[str, Any]:
    return RuntimeRecoveryEvidenceReplayValidationAttachment().attach(
        validation_report=validation_report,
        evidence_attachment=evidence_attachment,
    )


__all__ = [
    "RuntimeRecoveryEvidenceReplayValidationAttachment",
    "attach_recovery_evidence_to_replay_validation",
]
