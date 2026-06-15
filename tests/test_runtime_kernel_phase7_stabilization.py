from __future__ import annotations

from core.runtime.runtime_artifact_gate import RuntimeArtifactGate
from core.runtime.runtime_evidence_authority import RuntimeEvidenceAuthority
from core.runtime.runtime_authority_seal import _GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN
from core.runtime.runtime_events import RuntimeStateTransitionEvent
from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_reconstruction_pipeline import RuntimeReconstructionPipeline
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


def test_runtime_artifact_gate_seals_and_blocks_tampered_replay_artifact() -> None:
    gate = RuntimeArtifactGate()
    payload = {
        "runtime_version": RUNTIME_KERNEL_VERSION,
        "abi_version": RUNTIME_ABI_VERSION,
        "artifact_type": "runtime_replay_artifact",
        "replay_id": "replay:phase7",
        "session_snapshot": {"snapshot_id": "snapshot:phase7"},
        "journal_records": [],
    }

    sealed = gate.seal(payload, artifact_type="runtime_replay_artifact")
    allowed = gate.inspect(
        sealed,
        artifact_type="runtime_replay_artifact",
        abi_contract="runtime_replay_artifact",
    )
    assert allowed.allowed is True

    sealed["journal_records"].append({"tampered": True})
    blocked = gate.inspect(
        sealed,
        artifact_type="runtime_replay_artifact",
        abi_contract="runtime_replay_artifact",
        mutation_id="mutation:tampered",
    )
    assert blocked.allowed is False
    assert blocked.protection is not None
    assert blocked.protection.blocked is True


def test_runtime_evidence_authority_is_single_evidence_writer() -> None:
    authority = RuntimeEvidenceAuthority(
        evidence_id="evidence:phase7",
        issuer_token=_GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN,
    )
    authority.update(
        issuer_token=_GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN,
        stdout="ok",
        stderr="",
        runtime_traces=["start", "finalize"],
    )
    authority.merge_mapping(
        "rollback_snapshot",
        {"rollback_required": False},
        issuer_token=_GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN,
    )
    authority.append(
        "runtime_integrity",
        {"verified": True},
        issuer_token=_GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN,
    )

    snapshot = authority.snapshot().to_dict()
    assert snapshot["payload"]["stdout"] == "ok"
    assert snapshot["payload"]["rollback_snapshot"]["rollback_required"] is False
    assert snapshot["payload"]["runtime_integrity"][0]["verified"] is True


def test_runtime_reconstruction_pipeline_reconstructs_journal_state_and_gate() -> None:
    journal = RuntimeJournal()
    journal.append_event(
        RuntimeStateTransitionEvent(
            old_state="PENDING",
            new_state="SCANNING",
            reason="phase7",
        )
    )
    journal.append("runtime_memory_snapshot", payload={"snapshot_id": "memory:phase7"})
    journal.append("runtime_capability_graph", payload={"nodes": []})
    journal.append("runtime_intent_evaluation", payload={"allowed": True})

    report = RuntimeReconstructionPipeline(journal).reconstruct(replay_id="replay:phase7")
    payload = report.to_dict()

    assert payload["replay_id"] == "replay:phase7"
    assert payload["replayable"] is True
    assert [stage["name"] for stage in payload["stages"]] == [
        "journal_replay",
        "state_reconstruction",
        "memory_reconstruction",
        "capability_reconstruction",
        "scheduler_reconstruction",
        "distributed_reconstruction",
        "integrity_validation",
    ]
    assert payload["artifact_gate"]["allowed"] is True
