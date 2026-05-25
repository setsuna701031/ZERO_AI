from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime


TRUST_POLICY = {
    "policy_id": "worker-policy",
    "policy_version": "v1",
    "trusted_workers": [
        {
            "worker_id": "worker-alpha",
            "trust_key": "alpha-secret",
            "status": "active",
            "rotation": {"state": "active", "key_id": "alpha-key-v1"},
        }
    ],
}


def test_missing_worker_id_is_rejected() -> None:
    from core.runtime.distributed_worker_evidence_verifier import (
        DistributedWorkerEvidenceVerifier,
    )
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader

    blob = _signed_worker_blob("snapshot")
    blob.pop("worker_id")

    verification = DistributedWorkerEvidenceVerifier(TRUST_POLICY).verify(blob)
    loaded = ImportedEvidenceLoader(worker_trust_policy=TRUST_POLICY).load_record(
        blob,
        expected_slot="snapshot",
    )

    assert verification["ok"] is False
    assert "missing_worker_id" in verification["reasons"]
    assert loaded["ok"] is False
    assert loaded["record"]["normalized"] is False
    assert "worker_missing_worker_id" in loaded["reasons"]


def test_unknown_worker_id_is_rejected() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader

    blob = _signed_worker_blob("bundle", worker_id="worker-unknown", trust_key="unknown-secret")
    loaded = ImportedEvidenceLoader(worker_trust_policy=TRUST_POLICY).load_record(
        blob,
        expected_slot="bundle",
    )

    assert loaded["ok"] is False
    assert "worker_unknown_worker_id" in loaded["reasons"]
    assert loaded["record"]["normalized"] is False


def test_missing_signature_metadata_is_rejected() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader

    blob = _worker_blob("audit")
    loaded = ImportedEvidenceLoader(worker_trust_policy=TRUST_POLICY).load_record(
        blob,
        expected_slot="audit",
    )

    assert loaded["ok"] is False
    assert "worker_missing_signature_metadata" in loaded["reasons"]
    assert loaded["record"]["normalized"] is False


def test_invalid_signature_or_digest_mismatch_is_rejected() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader

    digest_mismatch = _signed_worker_blob("replay")
    digest_mismatch["plan_id"] = "tampered-after-signature"
    bad_signature = _signed_worker_blob("rollback")
    bad_signature["signature_metadata"]["signature"] = "worker-signature-invalid"

    loader = ImportedEvidenceLoader(worker_trust_policy=TRUST_POLICY)
    digest_result = loader.load_record(digest_mismatch, expected_slot="replay")
    signature_result = loader.load_record(bad_signature, expected_slot="rollback")

    assert digest_result["ok"] is False
    assert "worker_payload_digest_mismatch" in digest_result["reasons"]
    assert digest_result["record"]["normalized"] is False
    assert signature_result["ok"] is False
    assert "worker_invalid_signature" in signature_result["reasons"]
    assert signature_result["record"]["normalized"] is False


def test_producer_layer_alone_cannot_satisfy_evidence_seal() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer

    records = {
        slot: _worker_blob(slot)
        for slot in ("snapshot", "replay", "audit", "rollback", "bundle")
    }
    loaded = ImportedEvidenceLoader().load_records(records)
    summary = RuntimeEvidenceConsumer().read_records(records)

    assert loaded["ok"] is False
    assert set(loaded["invalid_records"]) == {"snapshot", "replay", "audit", "rollback", "bundle"}
    assert summary["ok"] is False
    assert summary["record_count"] == 0
    assert "unknown_or_untrusted_producer_layer" in summary["invalid_record_reasons"]["bundle"]


def test_verified_trusted_worker_evidence_is_normalized_and_consumed() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer
    from core.runtime.runtime_evidence_query import RuntimeEvidenceQuery

    loader = ImportedEvidenceLoader(worker_trust_policy=TRUST_POLICY)
    loaded = loader.load_records(_signed_worker_records())
    summary = RuntimeEvidenceConsumer().read_records(loaded["records"])
    sealed = RuntimeEvidenceQuery().sealed_state(summary)

    assert loaded["ok"] is True
    assert summary["ok"] is True
    assert sealed["sealed"] is True
    assert set(summary["record_classifications"].values()) == {"governed_execution_evidence"}
    for record in loaded["records"].values():
        assert record["normalized"] is True
        assert record["producer_layer"] == "governed_execution"
        assert record["source_producer_layer"] == "distributed_worker"
        assert record["validation"]["worker_signature_valid"] is True
        assert record["distributed_worker"]["worker_id"] == "worker-alpha"


def test_unverified_distributed_evidence_remains_rejected_by_consumer() -> None:
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer

    summary = RuntimeEvidenceConsumer().read_records(_signed_worker_records())

    assert summary["ok"] is False
    assert summary["record_count"] == 0
    assert set(summary["record_classifications"].values()) == {"external_imported_record"}
    assert "unknown_or_untrusted_producer_layer" in summary["invalid_record_reasons"]["snapshot"]


def _signed_worker_records() -> dict[str, dict[str, object]]:
    return {
        slot: _signed_worker_blob(slot)
        for slot in ("snapshot", "replay", "audit", "rollback", "bundle")
    }


def _signed_worker_blob(
    slot: str,
    *,
    worker_id: str = "worker-alpha",
    trust_key: str = "alpha-secret",
) -> dict[str, object]:
    from core.runtime.distributed_worker_evidence_verifier import (
        build_worker_signature_metadata,
    )

    blob = _worker_blob(slot, worker_id=worker_id)
    blob["signature_metadata"] = build_worker_signature_metadata(
        blob,
        worker_id=worker_id,
        trust_key=trust_key,
    )
    return blob


def _worker_blob(slot: str, *, worker_id: str = "worker-alpha") -> dict[str, object]:
    record_types = {
        "snapshot": "execution_plan_snapshot",
        "replay": "execution_replay_record",
        "audit": "execution_audit_record",
        "rollback": "rollback_verification_record",
        "bundle": "runtime_evidence_bundle",
    }
    blob: dict[str, object] = {
        "record_type": record_types[slot],
        "evidence_type": "governed_runtime_evidence",
        "artifact_class": "execution_evidence",
        "producer_layer": "distributed_worker",
        "worker_id": worker_id,
        "issued_at": datetime.now(UTC).isoformat(),
        "nonce": f"{worker_id}-{slot}-nonce",
        "provenance": {"source": f"worker://{worker_id}/{slot}.json"},
        "validation": deepcopy(
            {"validated": True, "provenance_checked": True, "seal_valid": True}
        ),
        "plan_id": "worker-plan",
        "snapshot_id": "worker-snapshot",
        "replay_id": "worker-replay",
        "audit_id": "worker-audit",
        "rollback_id": "worker-rollback",
        "bundle_id": "worker-bundle",
        "fingerprint": f"worker-{slot}-fingerprint",
        "aggregate_status": "succeeded",
        "verification_result": "verified",
    }
    if slot == "snapshot":
        blob["status"] = "succeeded"
        blob["execution_order"] = ["distributed_worker.step"]
    if slot == "rollback":
        blob["rollback_order"] = ["distributed_worker.step"]
    return blob
