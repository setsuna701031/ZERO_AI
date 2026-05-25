from __future__ import annotations

from copy import deepcopy


def test_direct_fake_evidence_blob_is_rejected_by_loader() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader

    result = ImportedEvidenceLoader().load_record(
        {
            "snapshot_id": "fake-snapshot",
            "plan_id": "fake-plan",
            "fingerprint": "shape-compatible",
            "status": "succeeded",
        },
        expected_slot="snapshot",
    )

    assert result["ok"] is False
    assert result["classification"] == "invalid_record"
    assert result["record"]["normalized"] is False
    assert "missing_record_type" in result["reasons"]
    assert "missing_producer_layer" in result["reasons"]


def test_missing_producer_layer_is_rejected_by_loader() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader

    blob = _blob("snapshot", producer_layer="")
    result = ImportedEvidenceLoader().load_record(blob, expected_slot="snapshot")

    assert result["ok"] is False
    assert result["record"]["normalized"] is False
    assert "missing_producer_layer" in result["reasons"]


def test_unknown_producer_layer_is_rejected_by_loader() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader

    blob = _blob("bundle", producer_layer="distributed_worker")
    result = ImportedEvidenceLoader().load_record(blob, expected_slot="bundle")

    assert result["ok"] is False
    assert result["classification"] == "external_imported_record"
    assert "unknown_or_untrusted_producer_layer" in result["reasons"]


def test_missing_provenance_source_is_rejected_by_loader() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader

    blob = _blob("audit")
    blob["provenance"] = {}
    result = ImportedEvidenceLoader().load_record(blob, expected_slot="audit")

    assert result["ok"] is False
    assert "missing_provenance" in result["reasons"]
    assert result["record"]["normalized"] is False


def test_output_artifact_remains_output_artifact_and_cannot_satisfy_seal() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer

    loader = ImportedEvidenceLoader()
    records = {
        slot: loader.load_record(
            _blob(slot, evidence_type="output_artifact", artifact_class="output_artifact", producer_layer="output_artifact"),
            expected_slot=slot,
        )["record"]
        for slot in ("snapshot", "replay", "audit", "rollback", "bundle")
    }
    summary = RuntimeEvidenceConsumer().read_records(records)

    assert summary["ok"] is False
    assert summary["record_count"] == 0
    assert set(summary["record_classifications"].values()) == {"output_artifact"}
    assert "output_artifact_not_execution_evidence" in records["bundle"]["loader"]["reasons"]


def test_validated_governed_execution_evidence_is_normalized_and_consumed() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer
    from core.runtime.runtime_evidence_query import RuntimeEvidenceQuery

    loader = ImportedEvidenceLoader()
    loaded = loader.load_records(_records())
    summary = RuntimeEvidenceConsumer().read_records(loaded["records"])
    sealed = RuntimeEvidenceQuery().sealed_state(summary)

    assert loaded["ok"] is True
    assert all(record["normalized"] is True for record in loaded["records"].values())
    assert all(record["loader"]["schema"] == loader.SCHEMA for record in loaded["records"].values())
    assert summary["ok"] is True
    assert summary["record_count"] == 5
    assert summary["invalid_records"] == []
    assert sealed["sealed"] is True


def test_consumer_still_rejects_unvalidated_external_records() -> None:
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer

    records = _records(validation={"validated": False, "provenance_checked": True, "seal_valid": True})

    summary = RuntimeEvidenceConsumer().read_records(records)

    assert summary["ok"] is False
    assert summary["record_count"] == 0
    assert "not_validated" in summary["invalid_record_reasons"]["snapshot"]


def test_loader_marks_records_normalized_only_after_validation() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader

    invalid = ImportedEvidenceLoader().load_record(
        _blob("replay", validation={"validated": False, "provenance_checked": True, "seal_valid": True}),
        expected_slot="replay",
    )
    valid = ImportedEvidenceLoader().load_record(_blob("replay"), expected_slot="replay")

    assert invalid["ok"] is False
    assert invalid["record"]["normalized"] is False
    assert valid["ok"] is True
    assert valid["record"]["normalized"] is True
    assert valid["record"]["artifact_class"] == "execution_evidence"


def _records(
    *,
    validation: dict[str, bool] | None = None,
) -> dict[str, dict[str, object]]:
    return {
        slot: _blob(slot, validation=validation)
        for slot in ("snapshot", "replay", "audit", "rollback", "bundle")
    }


def _blob(
    slot: str,
    *,
    evidence_type: str = "governed_runtime_evidence",
    artifact_class: str = "execution_evidence",
    producer_layer: str = "governed_execution",
    validation: dict[str, bool] | None = None,
) -> dict[str, object]:
    record_types = {
        "snapshot": "execution_plan_snapshot",
        "replay": "execution_replay_record",
        "audit": "execution_audit_record",
        "rollback": "rollback_verification_record",
        "bundle": "runtime_evidence_bundle",
    }
    blob: dict[str, object] = {
        "record_type": record_types[slot],
        "evidence_type": evidence_type,
        "artifact_class": artifact_class,
        "producer_layer": producer_layer,
        "provenance": {"source": f"import://evidence/{slot}.json"},
        "validation": deepcopy(
            validation
            if validation is not None
            else {"validated": True, "provenance_checked": True, "seal_valid": True}
        ),
        "plan_id": "plan-import",
        "snapshot_id": "snapshot-import",
        "replay_id": "replay-import",
        "audit_id": "audit-import",
        "rollback_id": "rollback-import",
        "bundle_id": "bundle-import",
        "fingerprint": f"{slot}-fingerprint",
        "aggregate_status": "succeeded",
        "verification_result": "verified",
    }
    if slot == "snapshot":
        blob["status"] = "succeeded"
        blob["execution_order"] = ["step_executor.execute"]
    if slot == "rollback":
        blob["rollback_order"] = ["step_executor.execute"]
    return blob
