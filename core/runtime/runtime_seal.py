from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from core.runtime.runtime_integrity import (
    RuntimeIntegrityReport,
    stable_fingerprint,
    utc_timestamp,
)
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


@dataclass(frozen=True)
class RuntimeSealSnapshot:
    seal_id: str
    artifact_type: str
    fingerprint: str
    runtime_version: str = RUNTIME_KERNEL_VERSION
    abi_version: str = RUNTIME_ABI_VERSION
    sealed_at: str = field(default_factory=utc_timestamp)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seal_id": self.seal_id,
            "artifact_type": self.artifact_type,
            "fingerprint": self.fingerprint,
            "runtime_version": self.runtime_version,
            "abi_version": self.abi_version,
            "sealed_at": self.sealed_at,
            "metadata": dict(self.metadata),
        }


def seal_runtime_artifact(
    payload: dict[str, Any],
    *,
    artifact_type: str,
    metadata: dict[str, Any] | None = None,
) -> RuntimeSealSnapshot:
    fingerprint = stable_fingerprint(payload)
    return RuntimeSealSnapshot(
        seal_id=f"runtime-seal-{fingerprint[:16]}",
        artifact_type=artifact_type,
        fingerprint=fingerprint,
        metadata=dict(metadata or {}),
    )


def attach_runtime_seal(
    payload: dict[str, Any],
    *,
    artifact_type: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sealed = copy.deepcopy(payload)
    sealed.setdefault("runtime_version", RUNTIME_KERNEL_VERSION)
    sealed.setdefault("abi_version", RUNTIME_ABI_VERSION)
    sealed["runtime_seal"] = seal_runtime_artifact(
        sealed,
        artifact_type=artifact_type,
        metadata=metadata,
    ).to_dict()
    return sealed


def verify_runtime_seal(payload: dict[str, Any], *, artifact_type: str = "") -> RuntimeIntegrityReport:
    seal = payload.get("runtime_seal")
    resolved_type = artifact_type or str(payload.get("artifact_type") or "runtime_artifact")
    actual = stable_fingerprint(payload)
    if not isinstance(seal, dict):
        return RuntimeIntegrityReport(
            artifact_type=resolved_type,
            verified=False,
            actual_fingerprint=actual,
            reason="runtime_seal_missing",
        )
    expected = str(seal.get("fingerprint") or "")
    if not expected:
        return RuntimeIntegrityReport(
            artifact_type=resolved_type,
            verified=False,
            actual_fingerprint=actual,
            reason="runtime_seal_fingerprint_missing",
        )
    if expected != actual:
        return RuntimeIntegrityReport(
            artifact_type=resolved_type,
            verified=False,
            expected_fingerprint=expected,
            actual_fingerprint=actual,
            reason="runtime_seal_mismatch",
        )
    return RuntimeIntegrityReport(
        artifact_type=resolved_type,
        verified=True,
        expected_fingerprint=expected,
        actual_fingerprint=actual,
        reason="runtime_seal_verified",
    )


__all__ = [
    "RuntimeSealSnapshot",
    "attach_runtime_seal",
    "seal_runtime_artifact",
    "verify_runtime_seal",
]
