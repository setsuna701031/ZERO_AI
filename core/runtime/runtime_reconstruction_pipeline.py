from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from core.runtime.runtime_artifact_gate import RuntimeArtifactGate, RuntimeArtifactGateReport
from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_replay_session import RuntimeReplayArtifact, RuntimeReplaySession
from core.runtime.runtime_serialization import DEFAULT_RUNTIME_SERIALIZER, RuntimeSerializationAuthority
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


@dataclass(frozen=True)
class RuntimeReconstructionStage:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    verified: bool = True
    reason: str = "runtime_reconstruction_stage_ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "name": self.name,
            "payload": copy.deepcopy(self.payload),
            "verified": self.verified,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RuntimeReconstructionReport:
    replay_id: str
    deterministic: bool
    replayable: bool
    stages: tuple[RuntimeReconstructionStage, ...]
    artifact_gate: RuntimeArtifactGateReport | None = None
    replay_artifact: RuntimeReplayArtifact | None = None
    canonical_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_reconstruction_report",
            "replay_id": self.replay_id,
            "deterministic": self.deterministic,
            "replayable": self.replayable,
            "stages": [stage.to_dict() for stage in self.stages],
            "artifact_gate": self.artifact_gate.to_dict() if self.artifact_gate else None,
            "replay_artifact": self.replay_artifact.to_dict() if self.replay_artifact else None,
            "canonical_fingerprint": self.canonical_fingerprint,
        }


class RuntimeReconstructionPipeline:
    """First-class reconstruction pipeline for journal/replay/session state."""

    def __init__(
        self,
        journal: RuntimeJournal,
        *,
        artifact_gate: RuntimeArtifactGate | None = None,
        serializer: RuntimeSerializationAuthority | None = None,
    ) -> None:
        self.journal = journal
        self.serializer = serializer or DEFAULT_RUNTIME_SERIALIZER
        self.artifact_gate = artifact_gate or RuntimeArtifactGate(serializer=self.serializer)

    def reconstruct(self, *, replay_id: str = "") -> RuntimeReconstructionReport:
        reconstruction = self.journal.reconstruct()
        integrity = reconstruction.get("integrity") or {}
        stages: list[RuntimeReconstructionStage] = [
            RuntimeReconstructionStage(
                "journal_replay",
                payload={
                    "record_count": reconstruction.get("record_count", 0),
                    "last_sequence": reconstruction.get("last_sequence", 0),
                    "integrity": integrity,
                },
                verified=bool(integrity.get("verified", False)),
                reason=str(integrity.get("reason") or "journal_reconstructed"),
            ),
            RuntimeReconstructionStage(
                "state_reconstruction",
                payload={"state_transitions": reconstruction.get("state_transitions", [])},
            ),
            RuntimeReconstructionStage(
                "memory_reconstruction",
                payload={"memory_snapshots": reconstruction.get("memory_snapshots", [])},
            ),
            RuntimeReconstructionStage(
                "capability_reconstruction",
                payload={"capability_state": reconstruction.get("capability_state", [])},
            ),
            RuntimeReconstructionStage(
                "scheduler_reconstruction",
                payload={"scheduler_state": reconstruction.get("scheduler_state", [])},
            ),
            RuntimeReconstructionStage(
                "distributed_reconstruction",
                payload={"distributed_state": reconstruction.get("distributed_state", [])},
            ),
        ]
        replay_artifact = RuntimeReplaySession(self.journal, replay_id=replay_id).reconstruct()
        replay_payload = self.serializer.normalize(
            replay_artifact.to_dict(),
            artifact_type="runtime_replay_artifact",
        )
        gate_report = self.artifact_gate.inspect(
            replay_payload,
            artifact_type="runtime_replay_artifact",
            abi_contract="runtime_replay_artifact",
            mutation_id=replay_artifact.replay_id,
        )
        stages.append(
            RuntimeReconstructionStage(
                "integrity_validation",
                payload={"artifact_gate": gate_report.to_dict()},
                verified=gate_report.allowed,
                reason=gate_report.reason,
            )
        )
        deterministic = all(stage.verified for stage in stages)
        report_seed = {
            "replay_id": replay_artifact.replay_id,
            "stages": [stage.to_dict() for stage in stages],
            "gate": gate_report.to_dict(),
        }
        return RuntimeReconstructionReport(
            replay_id=replay_artifact.replay_id,
            deterministic=deterministic,
            replayable=deterministic and replay_artifact.replayable,
            stages=tuple(stages),
            artifact_gate=gate_report,
            replay_artifact=replay_artifact,
            canonical_fingerprint=self.serializer.fingerprint(report_seed, artifact_type="runtime_reconstruction_report"),
        )


__all__ = [
    "RuntimeReconstructionPipeline",
    "RuntimeReconstructionReport",
    "RuntimeReconstructionStage",
]
