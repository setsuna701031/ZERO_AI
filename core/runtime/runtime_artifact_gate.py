from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Iterable

from core.runtime.runtime_abi import RuntimeABIValidation, validate_abi
from core.runtime.runtime_compatibility import RuntimeCompatibilityReport, check_runtime_compatibility
from core.runtime.runtime_integrity import RuntimeIntegrityReport
from core.runtime.runtime_seal import attach_runtime_seal, verify_runtime_seal
from core.runtime.runtime_self_protection import RuntimeProtectionDecision, RuntimeSelfProtectionController
from core.runtime.runtime_serialization import DEFAULT_RUNTIME_SERIALIZER, RuntimeSerializationAuthority
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


@dataclass(frozen=True)
class RuntimeArtifactGateReport:
    artifact_type: str
    allowed: bool
    sealed: bool
    abi: RuntimeABIValidation | None = None
    compatibility: RuntimeCompatibilityReport | None = None
    integrity: RuntimeIntegrityReport | None = None
    protection: RuntimeProtectionDecision | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    canonical_fingerprint: str = ""
    reason: str = "runtime_artifact_gate_allowed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": self.artifact_type,
            "allowed": self.allowed,
            "sealed": self.sealed,
            "abi": self.abi.to_dict() if self.abi else None,
            "compatibility": self.compatibility.to_dict() if self.compatibility else None,
            "integrity": self.integrity.to_dict() if self.integrity else None,
            "protection": self.protection.to_dict() if self.protection else None,
            "payload": copy.deepcopy(self.payload),
            "canonical_fingerprint": self.canonical_fingerprint,
            "reason": self.reason,
        }


class RuntimeArtifactGate:
    """Single authority for ABI, compatibility, seal, integrity, and quarantine checks."""

    def __init__(
        self,
        protection: RuntimeSelfProtectionController | None = None,
        serializer: RuntimeSerializationAuthority | None = None,
    ) -> None:
        self.protection = protection or RuntimeSelfProtectionController()
        self.serializer = serializer or DEFAULT_RUNTIME_SERIALIZER

    def seal(
        self,
        payload: dict[str, Any],
        *,
        artifact_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = self.serializer.normalize(payload, artifact_type=artifact_type)
        return attach_runtime_seal(normalized, artifact_type=artifact_type, metadata=metadata)

    def inspect(
        self,
        payload: dict[str, Any],
        *,
        artifact_type: str,
        abi_contract: str | None = None,
        require_seal: bool = True,
        mutation_id: str = "",
    ) -> RuntimeArtifactGateReport:
        working = self.serializer.normalize(payload, artifact_type=artifact_type)

        abi_report: RuntimeABIValidation | None = None
        if abi_contract:
            try:
                abi_report = validate_abi(abi_contract, working)
            except KeyError as exc:
                abi_report = RuntimeABIValidation(
                    contract_name=abi_contract,
                    version=RUNTIME_ABI_VERSION,
                    valid=False,
                    reason=f"runtime_abi_contract_unknown:{exc}",
                )

        compatibility = check_runtime_compatibility(working, artifact_type=artifact_type)
        integrity: RuntimeIntegrityReport | None = None
        sealed = isinstance(working.get("runtime_seal"), dict)
        if require_seal:
            integrity = verify_runtime_seal(working, artifact_type=artifact_type)

        protection_decision: RuntimeProtectionDecision | None = None
        if integrity is not None and not integrity.verified:
            protection_decision = self.protection.enforce_integrity(
                (integrity,),
                mutation_id=mutation_id,
            )

        allowed = True
        reason = "runtime_artifact_gate_allowed"
        if abi_report is not None and not abi_report.valid:
            allowed = False
            reason = abi_report.reason
        if not compatibility.compatible:
            allowed = False
            reason = compatibility.reason
        if integrity is not None and not integrity.verified:
            allowed = False
            reason = integrity.reason
        if protection_decision is not None and protection_decision.blocked:
            allowed = False
            reason = protection_decision.reason

        return RuntimeArtifactGateReport(
            artifact_type=artifact_type,
            allowed=allowed,
            sealed=sealed,
            abi=abi_report,
            compatibility=compatibility,
            integrity=integrity,
            protection=protection_decision,
            payload=working,
            canonical_fingerprint=self.serializer.fingerprint(working, artifact_type=artifact_type),
            reason=reason,
        )

    def inspect_many(
        self,
        artifacts: Iterable[tuple[str, dict[str, Any], str | None]],
        *,
        mutation_id: str = "",
        require_seal: bool = True,
    ) -> tuple[RuntimeArtifactGateReport, ...]:
        return tuple(
            self.inspect(
                payload,
                artifact_type=artifact_type,
                abi_contract=abi_contract,
                mutation_id=mutation_id,
                require_seal=require_seal,
            )
            for artifact_type, payload, abi_contract in artifacts
        )


__all__ = ["RuntimeArtifactGate", "RuntimeArtifactGateReport"]
