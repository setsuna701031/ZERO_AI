from __future__ import annotations

from copy import deepcopy


def test_shape_compatible_fake_evidence_is_rejected() -> None:
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer

    fake = {
        "snapshot_id": "snapshot-forged",
        "plan_id": "plan-forged",
        "fingerprint": "looks-like-a-fingerprint",
        "status": "succeeded",
    }

    summary = RuntimeEvidenceConsumer().read_records({"snapshot": fake})

    assert summary["ok"] is False
    assert summary["record_count"] == 0
    assert summary["invalid_records"] == ["snapshot"]
    assert summary["record_classifications"]["snapshot"] == "invalid_record"
    assert "missing_record_type" in summary["invalid_record_reasons"]["snapshot"]
    assert "missing_evidence_type" in summary["invalid_record_reasons"]["snapshot"]


def test_unsealed_external_artifact_cannot_satisfy_evidence_seal() -> None:
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer

    records = _records(
        evidence_type="output_artifact",
        producer_layer="output_artifact",
        validation={"validated": False, "provenance_checked": True, "seal_valid": False},
    )

    summary = RuntimeEvidenceConsumer().read_records(records)

    assert summary["ok"] is False
    assert summary["record_count"] == 0
    assert summary["invalid_records"] == ["snapshot", "replay", "audit", "rollback", "bundle"]
    assert set(summary["record_classifications"].values()) == {"output_artifact"}
    assert "unsupported_evidence_type" in summary["invalid_record_reasons"]["bundle"]
    assert "seal_not_validated" in summary["invalid_record_reasons"]["bundle"]


def test_missing_producer_layer_is_invalid() -> None:
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer

    records = _records(producer_layer="")

    summary = RuntimeEvidenceConsumer().read_records(records)

    assert summary["ok"] is False
    assert summary["record_count"] == 0
    assert summary["record_classifications"]["snapshot"] == "external_imported_record"
    assert "missing_producer_layer" in summary["invalid_record_reasons"]["snapshot"]


def test_unknown_producer_layer_is_invalid_for_imported_evidence() -> None:
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer
    from core.runtime.runtime_execution_result import build_runtime_execution_result

    records = _records(producer_layer="distributed_worker")
    summary = RuntimeEvidenceConsumer().read_records(records)
    execution = build_runtime_execution_result(
        {
            "ok": True,
            "executed": True,
            "execution_id": "external-worker-forged-exec",
            "status": "succeeded",
            "metadata": {
                "execution_source": "runtime_execution_gateway",
                "producer_layer": "distributed_worker",
            },
        }
    )

    assert summary["ok"] is False
    assert "unknown_or_untrusted_producer_layer" in summary["invalid_record_reasons"]["bundle"]
    assert execution["executed"] is False
    assert execution["execution_evidence"]["execution_legality"] == "denied"
    assert execution["execution_evidence"]["producer_layer"] == "distributed_worker"
    assert execution["execution_evidence"]["denial_reason"] == "producer_layer_mismatch:distributed_worker"


def test_normalized_governed_execution_evidence_can_satisfy_consumer_seal() -> None:
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer
    from core.runtime.runtime_evidence_query import RuntimeEvidenceQuery

    records = _records(producer_layer="governed_execution")

    summary = RuntimeEvidenceConsumer().read_records(
        records,
        seal_id="imported-governed-seal",
        seal_fingerprint="verified-import-fingerprint",
        emission_order=[
            {"type": "snapshot", "fingerprint": records["snapshot"]["fingerprint"]},
            {"type": "replay", "fingerprint": records["replay"]["fingerprint"]},
            {"type": "audit", "fingerprint": records["audit"]["fingerprint"]},
            {"type": "rollback", "fingerprint": records["rollback"]["fingerprint"]},
            {"type": "bundle", "fingerprint": records["bundle"]["fingerprint"]},
        ],
    )
    sealed_state = RuntimeEvidenceQuery().sealed_state(summary)

    assert summary["ok"] is True
    assert summary["record_count"] == 5
    assert summary["invalid_records"] == []
    assert set(summary["record_classifications"].values()) == {"governed_execution_evidence"}
    assert summary["can_replay"] is True
    assert summary["can_audit"] is True
    assert summary["can_rollback"] is True
    assert sealed_state["sealed"] is True


def test_imported_evidence_requires_explicit_validation_before_acceptance() -> None:
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer

    records = _records(
        validation={"validated": False, "provenance_checked": True, "seal_valid": True},
    )

    summary = RuntimeEvidenceConsumer().read_records(records)

    assert summary["ok"] is False
    assert summary["record_count"] == 0
    assert "not_validated" in summary["invalid_record_reasons"]["snapshot"]
    assert summary["record_classifications"]["snapshot"] == "external_imported_record"


def test_consumer_distinguishes_external_record_classes() -> None:
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer

    records = {
        "snapshot": _record("snapshot", producer_layer="governed_execution"),
        "replay": _record("replay", producer_layer="step_executor"),
        "audit": _record(
            "audit",
            evidence_type="output_artifact",
            producer_layer="output_artifact",
        ),
        "rollback": _record("rollback", producer_layer="external_import"),
        "bundle": {"record_type": "runtime_evidence_bundle"},
    }

    summary = RuntimeEvidenceConsumer().read_records(records)

    assert summary["ok"] is False
    assert summary["present_records"] == ["snapshot", "replay"]
    assert summary["record_classifications"] == {
        "snapshot": "governed_execution_evidence",
        "replay": "step_executor_execution_evidence",
        "audit": "output_artifact",
        "rollback": "external_imported_record",
        "bundle": "external_imported_record",
    }
    assert set(summary["invalid_records"]) == {"audit", "rollback", "bundle"}


def _records(
    *,
    evidence_type: str = "governed_runtime_evidence",
    producer_layer: str = "governed_execution",
    validation: dict[str, bool] | None = None,
) -> dict[str, dict[str, object]]:
    return {
        name: _record(
            name,
            evidence_type=evidence_type,
            producer_layer=producer_layer,
            validation=validation,
        )
        for name in ("snapshot", "replay", "audit", "rollback", "bundle")
    }


def _record(
    name: str,
    *,
    evidence_type: str = "governed_runtime_evidence",
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
    payload: dict[str, object] = {
        "record_type": record_types[name],
        "evidence_type": evidence_type,
        "producer_layer": producer_layer,
        "provenance": {"source": f"import://runtime/{name}.json"},
        "normalized": True,
        "validation": deepcopy(
            validation
            if validation is not None
            else {"validated": True, "provenance_checked": True, "seal_valid": True}
        ),
        "plan_id": "plan-imported",
        "snapshot_id": "snapshot-imported",
        "replay_id": "replay-imported",
        "audit_id": "audit-imported",
        "rollback_id": "rollback-imported",
        "bundle_id": "bundle-imported",
        "fingerprint": f"{name}-fingerprint",
        "aggregate_status": "succeeded",
        "verification_result": "verified",
    }
    if name == "snapshot":
        payload["status"] = "succeeded"
        payload["execution_order"] = ["step_executor.execute"]
    if name == "rollback":
        payload["rollback_order"] = ["step_executor.execute"]
    return payload
