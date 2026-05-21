from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


INTEGRITY_HASH_FIELD = "integrity_hash"
SEAL_FIELD = "runtime_seal"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_payload(value: Any, *, exclude_integrity: bool = True) -> Any:
    if isinstance(value, dict):
        return {
            str(key): canonical_payload(item, exclude_integrity=exclude_integrity)
            for key, item in sorted(value.items())
            if not exclude_integrity or key not in {INTEGRITY_HASH_FIELD, SEAL_FIELD}
        }
    if isinstance(value, (list, tuple)):
        return [canonical_payload(item, exclude_integrity=exclude_integrity) for item in value]
    if isinstance(value, set):
        return [canonical_payload(item, exclude_integrity=exclude_integrity) for item in sorted(value, key=str)]
    return copy.deepcopy(value)


def stable_fingerprint(value: Any, *, exclude_integrity: bool = True) -> str:
    encoded = json.dumps(
        canonical_payload(value, exclude_integrity=exclude_integrity),
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeIntegrityReport:
    artifact_type: str
    verified: bool
    expected_fingerprint: str = ""
    actual_fingerprint: str = ""
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "verified": self.verified,
            "expected_fingerprint": self.expected_fingerprint,
            "actual_fingerprint": self.actual_fingerprint,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


def attach_integrity(
    payload: dict[str, Any],
    *,
    artifact_type: str,
    runtime_version: str = RUNTIME_KERNEL_VERSION,
    abi_version: str = RUNTIME_ABI_VERSION,
) -> dict[str, Any]:
    sealed = copy.deepcopy(payload)
    sealed.setdefault("runtime_version", runtime_version)
    sealed.setdefault("abi_version", abi_version)
    sealed.setdefault("artifact_type", artifact_type)
    sealed[INTEGRITY_HASH_FIELD] = stable_fingerprint(sealed)
    return sealed


def verify_integrity(
    payload: dict[str, Any],
    *,
    artifact_type: str = "",
) -> RuntimeIntegrityReport:
    expected = str(payload.get(INTEGRITY_HASH_FIELD) or "")
    actual = stable_fingerprint(payload)
    resolved_type = artifact_type or str(payload.get("artifact_type") or "runtime_artifact")
    if not expected:
        return RuntimeIntegrityReport(
            artifact_type=resolved_type,
            verified=False,
            actual_fingerprint=actual,
            reason="integrity_hash_missing",
        )
    if expected != actual:
        return RuntimeIntegrityReport(
            artifact_type=resolved_type,
            verified=False,
            expected_fingerprint=expected,
            actual_fingerprint=actual,
            reason="integrity_hash_mismatch",
        )
    return RuntimeIntegrityReport(
        artifact_type=resolved_type,
        verified=True,
        expected_fingerprint=expected,
        actual_fingerprint=actual,
        reason="integrity_verified",
    )


__all__ = [
    "INTEGRITY_HASH_FIELD",
    "RuntimeIntegrityReport",
    "attach_integrity",
    "canonical_payload",
    "stable_fingerprint",
    "utc_timestamp",
    "verify_integrity",
]
