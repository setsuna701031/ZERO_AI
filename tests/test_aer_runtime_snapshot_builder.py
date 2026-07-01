from pathlib import Path

from core.runtime.aer_runtime_snapshot import (
    SNAPSHOT_CONTRACT,
    VALIDATION_ERROR_CATEGORIES,
    build_snapshot_from_resume_summary,
    snapshot_to_summary,
    validate_snapshot,
)


SNAPSHOT_MODULE = Path("core/runtime/aer_runtime_snapshot.py")


def _resume_summary(**overrides):
    summary = {
        "contract": "aer.runtime.resume_summary.v1",
        "valid": True,
        "outcome": "continue",
        "status": "valid",
        "reason": None,
    }
    summary.update(overrides)
    return summary


def test_snapshot_builder_module_exists():
    assert SNAPSHOT_MODULE.exists()


def test_snapshot_builder_has_no_forbidden_imports_or_surface_tokens():
    text = SNAPSHOT_MODULE.read_text(encoding="utf-8")

    for token in (
        "import os",
        "import random",
        "import time",
        "import uuid",
        "uuid4",
        "scheduler",
        "operator",
        "recovery",
        "audit",
        "journal",
        "dispatcher",
    ):
        assert token not in text


def test_build_snapshot_is_deterministic_for_same_resume_summary():
    summary = _resume_summary()

    first = build_snapshot_from_resume_summary(summary)
    second = build_snapshot_from_resume_summary(dict(reversed(list(summary.items()))))

    assert first == second


def test_build_snapshot_maps_resume_summary_to_snapshot_contract():
    snapshot = build_snapshot_from_resume_summary(_resume_summary())

    assert snapshot == {
        "contract": SNAPSHOT_CONTRACT,
        "snapshot_id": snapshot["snapshot_id"],
        "source_valid": True,
        "source_outcome": "continue",
        "source_status": "valid",
        "valid": True,
        "status": "valid",
        "outcome": "continue",
        "reason": None,
        "metadata": {},
    }


def test_build_snapshot_does_not_mutate_input():
    summary = _resume_summary()
    before = dict(summary)

    build_snapshot_from_resume_summary(summary)

    assert summary == before


def test_snapshot_id_is_deterministic_and_snapshot_owned():
    first = build_snapshot_from_resume_summary(_resume_summary())
    second = build_snapshot_from_resume_summary(_resume_summary())

    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["snapshot_id"].startswith("snapshot-v1-")


def test_required_identity_and_lineage_fields_are_preserved():
    snapshot = build_snapshot_from_resume_summary(
        _resume_summary(valid=False, outcome="continue", status="invalid", reason="invalid resume marker contract")
    )

    assert snapshot["contract"] == SNAPSHOT_CONTRACT
    assert snapshot["snapshot_id"].startswith("snapshot-v1-")
    assert snapshot["source_valid"] is False
    assert snapshot["source_outcome"] == "continue"
    assert snapshot["source_status"] == "invalid"


def test_status_vocabulary_follows_contract():
    valid_snapshot = build_snapshot_from_resume_summary(_resume_summary())
    invalid_upstream_snapshot = build_snapshot_from_resume_summary(
        _resume_summary(valid=False, status="invalid", reason="invalid resume marker contract")
    )

    assert valid_snapshot["status"] == "valid"
    assert valid_snapshot["valid"] is True
    assert invalid_upstream_snapshot["status"] == "invalid"
    assert invalid_upstream_snapshot["valid"] is False
    assert invalid_upstream_snapshot["reason"] == "invalid upstream contract"


def test_missing_required_resume_fields_produce_invalid_snapshot():
    summary = _resume_summary()
    del summary["status"]

    snapshot = build_snapshot_from_resume_summary(summary)

    assert snapshot["valid"] is False
    assert snapshot["status"] == "invalid"
    assert snapshot["reason"] == "invalid upstream contract"
    assert validate_snapshot(snapshot)["valid"] is True


def test_unknown_resume_fields_produce_invalid_snapshot_without_passthrough():
    snapshot = build_snapshot_from_resume_summary(_resume_summary(extra="ignored"))

    assert snapshot["valid"] is False
    assert "extra" not in snapshot
    assert set(snapshot) == {
        "contract",
        "snapshot_id",
        "source_valid",
        "source_outcome",
        "source_status",
        "valid",
        "status",
        "outcome",
        "reason",
        "metadata",
    }


def test_validate_snapshot_rejects_unknown_snapshot_fields():
    snapshot = build_snapshot_from_resume_summary(_resume_summary())
    snapshot["extra"] = "not allowed"

    report = validate_snapshot(snapshot)

    assert report["valid"] is False
    assert report["category"] == "Unknown Field Error"
    assert report["rejected"] is True


def test_validation_taxonomy_categories_exist():
    assert VALIDATION_ERROR_CATEGORIES == (
        "Schema Error",
        "Required Field Error",
        "Unknown Field Error",
        "Type Error",
        "Identity Error",
        "Lineage Error",
        "Status Error",
        "Consistency Error",
        "Version Error",
        "Determinism Error",
    )


def test_validation_report_is_descriptive_only():
    report = validate_snapshot({"contract": SNAPSHOT_CONTRACT})

    assert report["valid"] is False
    assert report["descriptive_only"] is True
    assert report["auto_repair_allowed"] is False


def test_snapshot_summary_projection_is_pure_public_summary():
    snapshot = build_snapshot_from_resume_summary(_resume_summary())

    assert snapshot_to_summary(snapshot) == {
        "contract": SNAPSHOT_CONTRACT,
        "valid": True,
        "status": "valid",
        "outcome": "continue",
        "reason": None,
    }


def test_no_runtime_integration_is_introduced():
    text = SNAPSHOT_MODULE.read_text(encoding="utf-8")

    assert "task_runner" not in text
    assert "runtime_dispatch" not in text
    assert "runtime_mainline" not in text
    assert "event_log" not in text
