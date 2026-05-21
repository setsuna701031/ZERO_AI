from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION, RUNTIME_SCHEMA_FAMILY


SUPPORTED_RUNTIME_MAJOR = "6"
SUPPORTED_ABI_VERSION = RUNTIME_ABI_VERSION


@dataclass(frozen=True)
class RuntimeCompatibilityReport:
    artifact_type: str
    compatible: bool
    runtime_version: str = ""
    abi_version: str = ""
    reason: str = ""
    migration_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "compatible": self.compatible,
            "runtime_version": self.runtime_version,
            "abi_version": self.abi_version,
            "reason": self.reason,
            "migration_required": self.migration_required,
            "metadata": dict(self.metadata),
        }


def check_runtime_compatibility(
    payload: dict[str, Any],
    *,
    artifact_type: str = "",
) -> RuntimeCompatibilityReport:
    resolved_type = artifact_type or str(payload.get("artifact_type") or "runtime_artifact")
    runtime_version = str(payload.get("runtime_version") or "")
    abi_version = str(payload.get("abi_version") or "")
    if not runtime_version or not abi_version:
        return RuntimeCompatibilityReport(
            artifact_type=resolved_type,
            compatible=False,
            runtime_version=runtime_version,
            abi_version=abi_version,
            reason="runtime_or_abi_version_missing",
        )
    if abi_version != SUPPORTED_ABI_VERSION:
        return RuntimeCompatibilityReport(
            artifact_type=resolved_type,
            compatible=False,
            runtime_version=runtime_version,
            abi_version=abi_version,
            reason="abi_version_incompatible",
            migration_required=True,
        )
    if runtime_version.split(".", 1)[0] != SUPPORTED_RUNTIME_MAJOR:
        return RuntimeCompatibilityReport(
            artifact_type=resolved_type,
            compatible=False,
            runtime_version=runtime_version,
            abi_version=abi_version,
            reason="runtime_major_version_incompatible",
            migration_required=True,
        )
    return RuntimeCompatibilityReport(
        artifact_type=resolved_type,
        compatible=True,
        runtime_version=runtime_version,
        abi_version=abi_version,
        reason="runtime_artifact_compatible",
        metadata={"current_runtime_version": RUNTIME_KERNEL_VERSION, "schema_family": RUNTIME_SCHEMA_FAMILY},
    )


def migration_hook(payload: dict[str, Any], *, target_runtime_version: str = RUNTIME_KERNEL_VERSION) -> dict[str, Any]:
    report = check_runtime_compatibility(payload)
    if report.compatible:
        return dict(payload)
    raise RuntimeError(
        f"runtime_migration_required:{report.artifact_type}:{report.runtime_version}->{target_runtime_version}"
    )


__all__ = [
    "RuntimeCompatibilityReport",
    "check_runtime_compatibility",
    "migration_hook",
]
