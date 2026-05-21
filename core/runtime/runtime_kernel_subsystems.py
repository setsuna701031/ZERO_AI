from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from core.runtime.runtime_artifact_gate import RuntimeArtifactGate, RuntimeArtifactGateReport
from core.runtime.runtime_evidence_authority import RuntimeEvidenceAuthority
from core.runtime.runtime_reconstruction_pipeline import RuntimeReconstructionPipeline, RuntimeReconstructionReport
from core.runtime.runtime_serialization import RuntimeSerializedArtifact, RuntimeSerializationAuthority
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


@dataclass(frozen=True)
class RuntimeSubsystemReport:
    subsystem: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "subsystem": self.subsystem,
            "status": self.status,
            "payload": dict(self.payload),
        }


class RuntimeLifecycleCoordinator:
    def __init__(self, transition: Callable[[str, str], Any], checkpoint: Callable[[str, dict[str, Any]], Any]) -> None:
        self._transition = transition
        self._checkpoint = checkpoint

    def transition(self, state: str, reason: str) -> RuntimeSubsystemReport:
        self._transition(state, reason)
        return RuntimeSubsystemReport("runtime_lifecycle", "transitioned", {"state": state, "reason": reason})

    def checkpoint(self, checkpoint_type: str, payload: dict[str, Any]) -> RuntimeSubsystemReport:
        self._checkpoint(checkpoint_type, payload)
        return RuntimeSubsystemReport("runtime_lifecycle", "checkpointed", {"checkpoint_type": checkpoint_type})


class RuntimeIntegrityCoordinator:
    def __init__(self, artifact_gate: RuntimeArtifactGate | None = None) -> None:
        self.artifact_gate = artifact_gate or RuntimeArtifactGate()

    def seal(self, payload: dict[str, Any], *, artifact_type: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.artifact_gate.seal(payload, artifact_type=artifact_type, metadata=metadata)

    def inspect(
        self,
        payload: dict[str, Any],
        *,
        artifact_type: str,
        abi_contract: str | None = None,
        mutation_id: str = "",
    ) -> RuntimeArtifactGateReport:
        return self.artifact_gate.inspect(
            payload,
            artifact_type=artifact_type,
            abi_contract=abi_contract,
            mutation_id=mutation_id,
        )


class RuntimeEvidenceCoordinator:
    def __init__(self, authority: RuntimeEvidenceAuthority) -> None:
        self.authority = authority

    def update(self, **values: Any) -> RuntimeSubsystemReport:
        self.authority.update(**values)
        return RuntimeSubsystemReport("runtime_evidence", "updated", {"keys": sorted(values)})

    def append(self, key: str, value: Any) -> RuntimeSubsystemReport:
        self.authority.append(key, value)
        return RuntimeSubsystemReport("runtime_evidence", "appended", {"key": key})

    def snapshot(self) -> dict[str, Any]:
        return self.authority.snapshot().to_dict()


class RuntimeReplayCoordinator:
    def __init__(self, pipeline: RuntimeReconstructionPipeline) -> None:
        self.pipeline = pipeline

    def reconstruct(self, *, replay_id: str = "") -> RuntimeReconstructionReport:
        return self.pipeline.reconstruct(replay_id=replay_id)


class RuntimeSerializationCoordinator:
    def __init__(self, authority: RuntimeSerializationAuthority | None = None) -> None:
        self.authority = authority or RuntimeSerializationAuthority()

    def serialize(
        self,
        payload: Any,
        *,
        artifact_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeSerializedArtifact:
        return self.authority.serialize(payload, artifact_type=artifact_type, metadata=metadata)

    def report(self, payload: Any, *, artifact_type: str) -> RuntimeSubsystemReport:
        serialized = self.serialize(payload, artifact_type=artifact_type)
        return RuntimeSubsystemReport(
            "runtime_serialization",
            "serialized",
            {
                "artifact_type": artifact_type,
                "fingerprint": serialized.fingerprint,
            },
        )


__all__ = [
    "RuntimeEvidenceCoordinator",
    "RuntimeIntegrityCoordinator",
    "RuntimeLifecycleCoordinator",
    "RuntimeReplayCoordinator",
    "RuntimeSerializationCoordinator",
    "RuntimeSubsystemReport",
]
