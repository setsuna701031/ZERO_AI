from __future__ import annotations

from datetime import UTC, datetime


def test_missing_trust_policy_rejects_distributed_evidence() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader

    result = ImportedEvidenceLoader().load_record(
        _signed_blob("snapshot"),
        expected_slot="snapshot",
    )

    assert result["ok"] is False
    assert "worker_policy_missing_trust_policy" in result["reasons"]
    assert result["record"]["normalized"] is False


def test_malformed_trust_policy_rejects_distributed_evidence() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader
    from core.runtime.runtime_trust_policy import validate_runtime_trust_policy

    malformed = {"trusted_workers": [{"worker_id": "worker-alpha", "trust_key": "alpha-secret"}]}
    validation = validate_runtime_trust_policy(malformed)
    result = ImportedEvidenceLoader(worker_trust_policy=malformed).load_record(
        _signed_blob("audit"),
        expected_slot="audit",
    )

    assert validation["ok"] is False
    assert "missing_policy_metadata" in validation["reasons"]
    assert result["ok"] is False
    assert "worker_policy_missing_policy_metadata" in result["reasons"]


def test_unknown_worker_rejects() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader

    result = ImportedEvidenceLoader(worker_trust_policy=_policy()).load_record(
        _signed_blob("bundle", worker_id="worker-unknown", trust_key="unknown-secret"),
        expected_slot="bundle",
    )

    assert result["ok"] is False
    assert "worker_unknown_worker_id" in result["reasons"]


def test_revoked_worker_rejects() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader

    result = ImportedEvidenceLoader(worker_trust_policy=_policy(status="revoked")).load_record(
        _signed_blob("replay"),
        expected_slot="replay",
    )

    assert result["ok"] is False
    assert "worker_revoked_worker_id" in result["reasons"]


def test_retired_key_rejects_new_evidence() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader

    result = ImportedEvidenceLoader(worker_trust_policy=_policy(status="retired")).load_record(
        _signed_blob("rollback"),
        expected_slot="rollback",
    )

    assert result["ok"] is False
    assert "worker_retired_trust_material" in result["reasons"]


def test_retired_key_can_be_allowed_for_historical_verification() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader

    result = ImportedEvidenceLoader(
        worker_trust_policy=_policy(status="retired"),
        historical_worker_verification=True,
    ).load_record(
        _signed_blob("rollback"),
        expected_slot="rollback",
    )

    assert result["ok"] is True
    assert result["record"]["distributed_worker"]["worker_state"] == "retired"
    assert result["record"]["distributed_worker"]["rotation"]["state"] == "retired"


def test_active_trusted_worker_evidence_validates_and_normalizes() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer
    from core.runtime.runtime_evidence_query import RuntimeEvidenceQuery

    loader = ImportedEvidenceLoader(worker_trust_policy=_policy())
    loaded = loader.load_records(_signed_records())
    summary = RuntimeEvidenceConsumer().read_records(loaded["records"])
    sealed = RuntimeEvidenceQuery().sealed_state(summary)

    assert loaded["ok"] is True
    assert summary["ok"] is True
    assert sealed["sealed"] is True
    assert loaded["records"]["bundle"]["distributed_worker"]["policy_id"] == "worker-policy"
    assert loaded["records"]["bundle"]["distributed_worker"]["policy_version"] == "v2"
    assert loaded["records"]["bundle"]["validation"]["worker_policy_id"] == "worker-policy"
    assert loaded["records"]["bundle"]["validation"]["worker_policy_version"] == "v2"


def _policy(*, status: str = "active") -> dict[str, object]:
    return {
        "policy_id": "worker-policy",
        "policy_version": "v2",
        "trusted_workers": [
            {
                "worker_id": "worker-alpha",
                "trust_key": "alpha-secret",
                "status": status,
                "rotation": {
                    "state": status,
                    "key_id": f"alpha-key-{status}",
                    "previous_key_id": "alpha-key-v1",
                },
            }
        ],
    }


def _signed_records() -> dict[str, dict[str, object]]:
    return {
        slot: _signed_blob(slot)
        for slot in ("snapshot", "replay", "audit", "rollback", "bundle")
    }


def _signed_blob(
    slot: str,
    *,
    worker_id: str = "worker-alpha",
    trust_key: str = "alpha-secret",
) -> dict[str, object]:
    from core.runtime.distributed_worker_evidence_verifier import build_worker_signature_metadata

    blob = _blob(slot, worker_id=worker_id)
    blob["signature_metadata"] = build_worker_signature_metadata(
        blob,
        worker_id=worker_id,
        trust_key=trust_key,
    )
    return blob


def _blob(slot: str, *, worker_id: str = "worker-alpha") -> dict[str, object]:
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
        "validation": {"validated": True, "provenance_checked": True, "seal_valid": True},
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
