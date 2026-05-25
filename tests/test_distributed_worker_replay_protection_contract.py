from __future__ import annotations

from datetime import UTC, datetime, timedelta


NOW = datetime(2026, 5, 25, 12, 0, 0, tzinfo=UTC)


def test_missing_timestamp_rejects() -> None:
    result = _load(_signed_blob("snapshot", issued_at=""))

    assert result["ok"] is False
    assert "worker_replay_missing_timestamp" in result["reasons"]


def test_stale_timestamp_rejects() -> None:
    result = _load(_signed_blob("replay", issued_at=(NOW - timedelta(seconds=301)).isoformat()))

    assert result["ok"] is False
    assert "worker_replay_stale_timestamp" in result["reasons"]


def test_future_timestamp_beyond_skew_rejects() -> None:
    result = _load(_signed_blob("audit", issued_at=(NOW + timedelta(seconds=31)).isoformat()))

    assert result["ok"] is False
    assert "worker_replay_future_timestamp" in result["reasons"]


def test_missing_nonce_or_evidence_id_rejects() -> None:
    result = _load(_signed_blob("rollback", nonce=""))

    assert result["ok"] is False
    assert "worker_replay_missing_nonce" in result["reasons"]


def test_reused_nonce_or_evidence_id_rejects_replay() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader
    from core.runtime.runtime_replay_protection import RuntimeReplayProtection

    replay = RuntimeReplayProtection(now=NOW)
    loader = ImportedEvidenceLoader(worker_trust_policy=_policy(), replay_protection=replay)
    first = loader.load_record(_signed_blob("bundle", nonce="nonce-reused"), expected_slot="bundle")
    second = loader.load_record(_signed_blob("bundle", nonce="nonce-reused"), expected_slot="bundle")

    assert first["ok"] is True
    assert second["ok"] is False
    assert "worker_replay_reused_nonce" in second["reasons"]


def test_valid_fresh_unique_nonce_normalizes_and_records_metadata() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer
    from core.runtime.runtime_evidence_query import RuntimeEvidenceQuery
    from core.runtime.runtime_replay_protection import RuntimeReplayProtection

    records = {
        slot: _signed_blob(slot, nonce=f"nonce-{slot}")
        for slot in ("snapshot", "replay", "audit", "rollback", "bundle")
    }
    loader = ImportedEvidenceLoader(
        worker_trust_policy=_policy(),
        replay_protection=RuntimeReplayProtection(now=NOW),
    )
    loaded = loader.load_records(records)
    summary = RuntimeEvidenceConsumer().read_records(loaded["records"])
    sealed = RuntimeEvidenceQuery().sealed_state(summary)

    assert loaded["ok"] is True
    assert summary["ok"] is True
    assert sealed["sealed"] is True
    bundle = loaded["records"]["bundle"]
    assert bundle["validation"]["worker_nonce"] == "nonce-bundle"
    assert bundle["validation"]["worker_timestamp"] == NOW.isoformat()
    assert bundle["distributed_worker"]["policy_id"] == "worker-policy"
    assert bundle["distributed_worker"]["policy_version"] == "v4"
    assert bundle["distributed_worker"]["worker_id"] == "worker-alpha"


def _load(blob: dict[str, object]) -> dict[str, object]:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader
    from core.runtime.runtime_replay_protection import RuntimeReplayProtection

    return ImportedEvidenceLoader(
        worker_trust_policy=_policy(),
        replay_protection=RuntimeReplayProtection(now=NOW),
    ).load_record(blob, expected_slot=str(blob["slot"]))


def _policy() -> dict[str, object]:
    return {
        "policy_id": "worker-policy",
        "policy_version": "v4",
        "trusted_workers": [
            {
                "worker_id": "worker-alpha",
                "trust_key": "alpha-secret",
                "status": "active",
                "rotation": {"state": "active", "key_id": "alpha-key-v4"},
            }
        ],
    }


def _signed_blob(
    slot: str,
    *,
    issued_at: str | None = None,
    nonce: str | None = None,
) -> dict[str, object]:
    from core.runtime.distributed_worker_evidence_verifier import build_worker_signature_metadata

    blob = _blob(
        slot,
        issued_at=NOW.isoformat() if issued_at is None else issued_at,
        nonce=f"nonce-{slot}" if nonce is None else nonce,
    )
    blob["signature_metadata"] = build_worker_signature_metadata(
        blob,
        worker_id="worker-alpha",
        trust_key="alpha-secret",
    )
    return blob


def _blob(slot: str, *, issued_at: str, nonce: str) -> dict[str, object]:
    record_types = {
        "snapshot": "execution_plan_snapshot",
        "replay": "execution_replay_record",
        "audit": "execution_audit_record",
        "rollback": "rollback_verification_record",
        "bundle": "runtime_evidence_bundle",
    }
    blob: dict[str, object] = {
        "slot": slot,
        "record_type": record_types[slot],
        "evidence_type": "governed_runtime_evidence",
        "artifact_class": "execution_evidence",
        "producer_layer": "distributed_worker",
        "worker_id": "worker-alpha",
        "issued_at": issued_at,
        "nonce": nonce,
        "provenance": {"source": f"worker://worker-alpha/{slot}.json"},
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
