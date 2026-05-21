from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.runtime.runtime_artifact_gate import RuntimeArtifactGate
from core.runtime.runtime_bypass_audit import RuntimeBypassAuditReport, audit_runtime_paths, audit_runtime_texts
from core.runtime.runtime_serialization import DEFAULT_RUNTIME_SERIALIZER, RuntimeSerializationAuthority
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


@dataclass(frozen=True)
class RuntimeSerializationFreezeManifest:
    artifact_types: tuple[str, ...]
    fingerprints: dict[str, str]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def deterministic(self) -> bool:
        return bool(self.artifact_types) and all(self.fingerprints.get(item) for item in self.artifact_types)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_serialization_freeze_manifest",
            "deterministic": self.deterministic,
            "artifact_types": list(self.artifact_types),
            "fingerprints": dict(self.fingerprints),
            "metadata": copy.deepcopy(self.metadata),
        }


@dataclass(frozen=True)
class RuntimeFreezeHardeningReport:
    bypass_audit: RuntimeBypassAuditReport
    serialization_manifest: RuntimeSerializationFreezeManifest
    artifact_gate_reports: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.bypass_audit.passed and self.serialization_manifest.deterministic and all(
            bool(report.get("allowed", False)) for report in self.artifact_gate_reports
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_freeze_hardening_report",
            "passed": self.passed,
            "bypass_audit": self.bypass_audit.to_dict(),
            "serialization_manifest": self.serialization_manifest.to_dict(),
            "artifact_gate_reports": [copy.deepcopy(report) for report in self.artifact_gate_reports],
            "metadata": copy.deepcopy(self.metadata),
        }


class RuntimeFreezeHardeningController:
    """Freeze hardening entrypoint.

    This controller is intentionally small: it does not add runtime features.
    It verifies that freeze-candidate code routes artifacts through the kernel
    authorities instead of silently reintroducing bypass paths.
    """

    def __init__(
        self,
        *,
        serializer: RuntimeSerializationAuthority | None = None,
        artifact_gate: RuntimeArtifactGate | None = None,
    ) -> None:
        self.serializer = serializer or DEFAULT_RUNTIME_SERIALIZER
        self.artifact_gate = artifact_gate or RuntimeArtifactGate(serializer=self.serializer)

    def build_serialization_manifest(
        self,
        artifacts: Mapping[str, Any],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeSerializationFreezeManifest:
        fingerprints: dict[str, str] = {}
        for artifact_type, payload in sorted(artifacts.items(), key=lambda item: item[0]):
            fingerprints[str(artifact_type)] = self.serializer.fingerprint(
                payload,
                artifact_type=str(artifact_type),
            )
        return RuntimeSerializationFreezeManifest(
            artifact_types=tuple(sorted(str(item) for item in artifacts.keys())),
            fingerprints=fingerprints,
            metadata=dict(metadata or {}),
        )

    def inspect_artifacts(self, artifacts: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
        reports: list[dict[str, Any]] = []
        for artifact_type, payload in sorted(artifacts.items(), key=lambda item: item[0]):
            sealed = self.artifact_gate.seal(dict(payload or {}), artifact_type=str(artifact_type))
            reports.append(
                self.artifact_gate.inspect(
                    sealed,
                    artifact_type=str(artifact_type),
                    require_seal=True,
                ).to_dict()
            )
        return tuple(reports)

    def audit_texts(
        self,
        texts: Mapping[str, str],
        *,
        artifacts: Mapping[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeFreezeHardeningReport:
        artifact_payloads = dict(artifacts or {"runtime_freeze_probe": {"phase": "freeze_hardening"}})
        return RuntimeFreezeHardeningReport(
            bypass_audit=audit_runtime_texts(texts, metadata=metadata),
            serialization_manifest=self.build_serialization_manifest(artifact_payloads, metadata=metadata),
            artifact_gate_reports=self.inspect_artifacts(artifact_payloads),
            metadata=dict(metadata or {}),
        )

    def audit_paths(
        self,
        paths: Iterable[str | Path],
        *,
        artifacts: Mapping[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeFreezeHardeningReport:
        artifact_payloads = dict(artifacts or {"runtime_freeze_probe": {"phase": "freeze_hardening"}})
        return RuntimeFreezeHardeningReport(
            bypass_audit=audit_runtime_paths(paths, metadata=metadata),
            serialization_manifest=self.build_serialization_manifest(artifact_payloads, metadata=metadata),
            artifact_gate_reports=self.inspect_artifacts(artifact_payloads),
            metadata=dict(metadata or {}),
        )


__all__ = [
    "RuntimeFreezeHardeningController",
    "RuntimeFreezeHardeningReport",
    "RuntimeSerializationFreezeManifest",
]
