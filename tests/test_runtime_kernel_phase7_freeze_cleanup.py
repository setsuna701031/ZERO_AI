from __future__ import annotations

from core.runtime.runtime_artifact_gate import RuntimeArtifactGate
from core.runtime.runtime_evidence_authority import RuntimeEvidenceAuthority
from core.runtime.runtime_events import RuntimeStateTransitionEvent
from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_reconstruction_pipeline import RuntimeReconstructionPipeline
from core.runtime.runtime_serialization import RuntimeSerializationAuthority
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


def test_runtime_serialization_is_deterministic_and_versioned() -> None:
    serializer = RuntimeSerializationAuthority()
    left = {"z": 1, "a": {"b": 2}}
    right = {"a": {"b": 2}, "z": 1}

    serialized_left = serializer.serialize(left, artifact_type="runtime_test_artifact")
    serialized_right = serializer.serialize(right, artifact_type="runtime_test_artifact")

    assert serialized_left.fingerprint == serialized_right.fingerprint
    assert serialized_left.payload["runtime_version"] == RUNTIME_KERNEL_VERSION
    assert serialized_left.payload["abi_version"] == RUNTIME_ABI_VERSION
    assert serialized_left.payload["artifact_type"] == "runtime_test_artifact"


def test_artifact_gate_uses_canonical_serialization_and_reports_fingerprint() -> None:
    gate = RuntimeArtifactGate()
    payload = gate.seal(
        {"payload": {"b": 2, "a": 1}},
        artifact_type="runtime_replay_artifact",
    )
    payload.update(
        {
            "replay_id": "replay:test",
            "session_snapshot": {},
            "journal_records": [],
        }
    )
    payload = gate.seal(payload, artifact_type="runtime_replay_artifact")

    report = gate.inspect(
        payload,
        artifact_type="runtime_replay_artifact",
        abi_contract="runtime_replay_artifact",
    )

    assert report.allowed is True
    assert report.sealed is True
    assert report.canonical_fingerprint
    assert report.compatibility is not None
    assert report.compatibility.to_dict()["compatible"] is True


def test_evidence_authority_preserves_phase6_runtime_compatibility_shape() -> None:
    authority = RuntimeEvidenceAuthority(evidence_id="evidence:test")
    authority.append(
        "runtime_compatibility",
        {
            "artifact_type": "runtime_execution_result",
            "compatible": True,
            "reason": "ok",
        },
    )
    authority.append(
        "runtime_compatibility",
        {
            "compatibility": {
                "artifact_type": "runtime_replay_artifact",
                "compatible": True,
                "reason": "wrapped_gate_report_canonicalized",
            }
        },
    )

    payload = authority.to_dict()

    assert payload["runtime_compatibility"]
    assert all("compatible" in report for report in payload["runtime_compatibility"])
    assert all(report["compatible"] is True for report in payload["runtime_compatibility"])
    assert all(report["runtime_version"] == RUNTIME_KERNEL_VERSION for report in payload["runtime_compatibility"])
    assert all(report["abi_version"] == RUNTIME_ABI_VERSION for report in payload["runtime_compatibility"])


def test_reconstruction_pipeline_emits_canonical_fingerprint() -> None:
    journal = RuntimeJournal()
    journal.append_event(
        RuntimeStateTransitionEvent(
            old_state="PENDING",
            new_state="SCANNING",
            reason="phase7 freeze cleanup",
        )
    )

    report = RuntimeReconstructionPipeline(journal).reconstruct(replay_id="replay:phase7-freeze")
    payload = report.to_dict()

    assert report.deterministic is True
    assert report.replayable is True
    assert payload["canonical_fingerprint"]
    assert payload["artifact_gate"]["allowed"] is True
    assert any(stage["name"] == "integrity_validation" for stage in payload["stages"])
