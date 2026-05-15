from __future__ import annotations

import copy
import json
from typing import Any

from core.runtime.runtime_evidence_bundle import RuntimeEvidenceBundle
from core.runtime.runtime_recovery_audit_artifact import (
    build_runtime_recovery_audit_artifact,
)


class RuntimeRecoveryEvidenceAttachmentRejected(RuntimeError):
    pass


class RuntimeRecoveryEvidenceAttachment:
    SCHEMA = "zero.runtime.recovery_evidence_attachment.v1"

    def attach(
        self,
        *,
        bundle: RuntimeEvidenceBundle,
        source: Any,
        audit_id: str = "",
        recovery_id: str = "",
    ) -> dict[str, Any]:
        if not isinstance(bundle, RuntimeEvidenceBundle):
            raise RuntimeRecoveryEvidenceAttachmentRejected(
                "bundle must be RuntimeEvidenceBundle"
            )

        artifact = build_runtime_recovery_audit_artifact(
            source,
            audit_id=audit_id,
            recovery_id=recovery_id,
        )

        payload = {
            "schema": self.SCHEMA,
            "bundle_id": bundle.bundle_id,
            "plan_id": bundle.plan_id,
            "snapshot_id": bundle.snapshot_id,
            "aggregate_status": bundle.aggregate_status,
            "bundle_fingerprint": bundle.fingerprint,
            "recovery_artifact": copy.deepcopy(artifact),
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


def attach_runtime_recovery_evidence(
    *,
    bundle: RuntimeEvidenceBundle,
    source: Any,
    audit_id: str = "",
    recovery_id: str = "",
) -> dict[str, Any]:
    return RuntimeRecoveryEvidenceAttachment().attach(
        bundle=bundle,
        source=source,
        audit_id=audit_id,
        recovery_id=recovery_id,
    )


__all__ = [
    "RuntimeRecoveryEvidenceAttachment",
    "RuntimeRecoveryEvidenceAttachmentRejected",
    "attach_runtime_recovery_evidence",
]
