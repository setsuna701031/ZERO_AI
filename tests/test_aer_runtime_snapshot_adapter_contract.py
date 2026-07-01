from pathlib import Path

from core.runtime import aer_runtime_snapshot
from core.runtime.aer_runtime_snapshot import build_snapshot_from_resume_summary


SNAPSHOT_SPEC = Path("docs/contracts/runtime/snapshot_v1.md")
SNAPSHOT_MODULE = Path("core/runtime/aer_runtime_snapshot.py")


def test_snapshot_spec_defines_resume_summary_adapter_contract():
    assert SNAPSHOT_SPEC.exists()

    text = SNAPSHOT_SPEC.read_text(encoding="utf-8")

    assert "Resume Summary Adapter Contract" in text
    assert "aer.runtime.resume_summary.v1" in text
    assert "aer.runtime.snapshot.v1" in text


def test_adapter_contract_seals_identity_and_lineage_fields():
    text = SNAPSHOT_SPEC.read_text(encoding="utf-8")

    assert "Required identity fields" in text
    assert "input `contract` must be `aer.runtime.resume_summary.v1`" in text
    assert "output `contract` must be `aer.runtime.snapshot.v1`" in text
    assert "output `snapshot_id` must be Snapshot-owned identity" in text

    assert "Required lineage fields" in text
    assert "output `source_valid` maps from input `valid`" in text
    assert "output `source_outcome` maps from input `outcome`" in text
    assert "output `source_status` maps from input `status`" in text


def test_adapter_contract_defines_complete_field_level_mapping_table():
    text = SNAPSHOT_SPEC.read_text(encoding="utf-8")

    assert "Field-level mapping table" in text
    assert "Resume Summary field" in text
    assert "Snapshot field" in text
    assert "Required / Optional" in text
    assert "Mapping rule" in text
    assert "Default behavior" in text
    assert "Invalid-input behavior" in text

    for snapshot_field in (
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
        assert snapshot_field in text

    assert "copied directly" in text
    assert "derived" in text
    assert "constant" in text
    assert "prohibited" in text
    assert "Every Snapshot v1 field is defined by this table" in text
    assert "There are no undefined Snapshot fields" in text


def test_adapter_contract_requires_deterministic_future_implementation():
    text = SNAPSHOT_SPEC.read_text(encoding="utf-8")

    assert "fully deterministic" in text
    assert "same Resume Summary input shall always produce the identical Snapshot payload" in text


def test_adapter_contract_forbids_runtime_behaviors_and_side_effects():
    text = SNAPSHOT_SPEC.read_text(encoding="utf-8")

    assert "Forbidden fields" in text
    assert "No side effects rule" in text
    assert "IO" in text
    assert "storage" in text
    assert "replay" in text
    assert "recovery" in text
    assert "runtime execution" in text
    assert "operator loop behavior" in text


def test_adapter_contract_defines_missing_and_invalid_input_behavior():
    text = SNAPSHOT_SPEC.read_text(encoding="utf-8")

    assert "Missing-field behavior" in text
    assert "missing input `contract`, `valid`, `outcome`, `status`, or `reason` is invalid input" in text
    assert "Invalid-input behavior" in text
    assert "non-dict input is invalid input" in text
    assert "invalid upstream contract" in text


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


def test_package_120_snapshot_module_remains_pure_deterministic_builder():
    resume_summary = {
        "contract": "aer.runtime.resume_summary.v1",
        "valid": True,
        "outcome": "continue",
        "status": "valid",
        "reason": None,
    }

    first = build_snapshot_from_resume_summary(resume_summary)
    second = build_snapshot_from_resume_summary(dict(reversed(list(resume_summary.items()))))

    assert first == second


def test_package_120_snapshot_module_has_no_runtime_integration_dependencies():
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
