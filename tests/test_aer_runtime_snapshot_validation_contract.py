from pathlib import Path

from core.runtime import aer_runtime_snapshot
from core.runtime.aer_runtime_snapshot import build_snapshot_from_resume_summary, validate_snapshot


SNAPSHOT_SPEC = Path("docs/contracts/runtime/snapshot_v1.md")
SNAPSHOT_MODULE = Path("core/runtime/aer_runtime_snapshot.py")


def test_snapshot_spec_defines_validation_contract():
    assert SNAPSHOT_SPEC.exists()

    text = SNAPSHOT_SPEC.read_text(encoding="utf-8")

    assert "Snapshot Validation Contract" in text
    assert "aer.runtime.snapshot.v1" in text


def test_snapshot_validation_contract_defines_required_validation_rules():
    text = SNAPSHOT_SPEC.read_text(encoding="utf-8")

    assert "Structural validation" in text
    assert "Required fields" in text
    assert "Allowed / unknown field policy" in text
    assert "unknown fields are prohibited" in text
    assert "Schema version rule" in text
    assert "Identity validation" in text
    assert "Lineage validation" in text
    assert "Status vocabulary validation" in text
    assert "Consistency validation" in text
    assert "Deterministic validation rule" in text
    assert "Invalid snapshot behavior" in text


def test_snapshot_validation_contract_defines_canonical_error_taxonomy():
    text = SNAPSHOT_SPEC.read_text(encoding="utf-8")

    assert "Canonical validation error taxonomy" in text
    assert "Each validation failure must belong to exactly one category" in text
    assert "Trigger condition" in text
    assert "Contract consequence" in text
    assert "Snapshot rejected" in text
    assert "Future auto-repair allowed" in text

    for category in (
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
    ):
        assert category in text

    assert "Validation reports are descriptive only" in text
    assert "must not perform mutation, repair, replay, persistence, recovery" in text


def test_snapshot_validation_contract_defines_required_public_fields():
    text = SNAPSHOT_SPEC.read_text(encoding="utf-8")

    for field in (
        "`contract`",
        "`snapshot_id`",
        "`source_valid`",
        "`source_outcome`",
        "`source_status`",
        "`valid`",
        "`status`",
        "`outcome`",
        "`reason`",
        "`metadata`",
    ):
        assert field in text


def test_snapshot_validation_contract_defines_v2_compatibility_boundary():
    text = SNAPSHOT_SPEC.read_text(encoding="utf-8")

    assert "Compatibility boundary for future v2 migration" in text
    assert "future Snapshot v2 payloads must use a distinct contract value" in text
    assert "v2 migration must define a dedicated v2 contract before implementation" in text
    assert "must not infer, upgrade, downgrade, coerce, or silently accept v2 fields" in text


def test_snapshot_validation_contract_forbids_runtime_behaviors_and_side_effects():
    text = SNAPSHOT_SPEC.read_text(encoding="utf-8")

    assert "No side effects rule" in text
    assert "IO" in text
    assert "storage" in text
    assert "replay" in text
    assert "recovery" in text
    assert "runtime execution" in text
    assert "operator loop behavior" in text


def test_snapshot_implementation_module_is_snapshot_boundary_only():
    assert SNAPSHOT_MODULE.exists()

    assert aer_runtime_snapshot.__all__ == [
        "RESUME_SUMMARY_CONTRACT",
        "SNAPSHOT_CONTRACT",
        "VALIDATION_ERROR_CATEGORIES",
        "build_snapshot_from_resume_summary",
        "validate_snapshot",
        "snapshot_to_summary",
    ]


def test_package_120_validation_module_remains_descriptive_and_deterministic():
    snapshot = build_snapshot_from_resume_summary(
        {
            "contract": "aer.runtime.resume_summary.v1",
            "valid": True,
            "outcome": "continue",
            "status": "valid",
            "reason": None,
        }
    )
    invalid_snapshot = dict(snapshot)
    invalid_snapshot["extra"] = "not allowed"

    first = validate_snapshot(invalid_snapshot)
    second = validate_snapshot(dict(invalid_snapshot))

    assert first == second
    assert first["descriptive_only"] is True
    assert first["auto_repair_allowed"] is False
    assert invalid_snapshot["extra"] == "not allowed"


def test_package_120_validation_module_has_no_runtime_integration_dependencies():
    text = SNAPSHOT_MODULE.read_text(encoding="utf-8")

    for token in (
        "scheduler",
        "operator",
        "recovery",
        "replay",
        "audit",
        "journal",
        "persistence",
        "dispatcher",
        "task_runner",
        "runtime_mainline",
    ):
        assert token not in text
