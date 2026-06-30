from __future__ import annotations

from typing import Any


import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]

def test_replay_like_external_records_cannot_be_used_as_execution_evidence() -> None:
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer

    records = {
        "snapshot": {
            "record_type": "execution_plan_snapshot",
            "producer_layer": "external",
            "normalized": False,
        },
        "replay": {
            "record_type": "execution_replay_record",
            "producer_layer": "external",
            "normalized": False,
        },
        "audit": {
            "record_type": "execution_audit_record",
            "producer_layer": "external",
            "normalized": False,
        },
        "rollback": {
            "record_type": "rollback_verification_record",
            "producer_layer": "external",
            "normalized": False,
        },
        "bundle": {
            "record_type": "runtime_evidence_bundle",
            "producer_layer": "external",
            "normalized": False,
        },
    }

    summary = RuntimeEvidenceConsumer().read_records(records)

    assert summary["ok"] is False
    assert summary["record_count"] == 0
    assert set(summary["invalid_records"]) == {
        "snapshot",
        "replay",
        "audit",
        "rollback",
        "bundle",
    }


def test_runtime_replay_constitution_summary_is_readonly() -> None:
    from core.runtime.runtime_replay_engine import replay_constitution_summary

    summary = replay_constitution_summary(
        replay_id="repair-replay-legality",
        parent_replay_lineage=["root-replay"],
        source_runtime_state_refs=[{"state_id": "runtime-state-1"}],
        transition={
            "transition_allowed": True,
            "transition_reason": "readonly replay validation",
        },
        metadata={"purpose": "repair_replay_legality_contract"},
    )

    assert isinstance(summary, dict)
    assert "continuity_verified" in summary
    assert summary["replay_constitution_status"] in {
        "canonical",
        "review_required",
        "block_recommended",
    }
    assert "execution_authority" not in summary


def test_repair_replay_legality_keeps_output_artifacts_out_of_evidence() -> None:
    output_artifact = {
        "artifact_class": "output_artifact",
        "producer_layer": "agent_loop",
        "record_type": "repair_replay_visibility_artifact",
        "sealed_execution_evidence": False,
    }

    assert output_artifact["artifact_class"] == "output_artifact"
    assert output_artifact["sealed_execution_evidence"] is False
    assert output_artifact["producer_layer"] != "step_executor"


def test_imported_replay_bundle_requires_normalized_validation() -> None:
    from core.runtime.imported_evidence_loader import ImportedEvidenceLoader

    loader = ImportedEvidenceLoader()
    result = loader.load_record(
        {
            "record_type": "execution_replay_record",
            "evidence_type": "governed_runtime_evidence",
            "artifact_class": "execution_evidence",
            "producer_layer": "external",
            "provenance": {"source": "file://fake-replay.json"},
            "validation": {
                "validated": True,
                "provenance_checked": True,
                "seal_valid": True,
            },
        },
        expected_slot="replay",
    )

    assert result["ok"] is False
    assert result["record"]["normalized"] is False
    assert "unknown_or_untrusted_producer_layer" in result["reasons"]


