from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


FORENSIC_REPORT_REQUIRED_FIELDS: Tuple[str, ...] = (
    "stack_version",
    "report_id",
    "timeline_entries",
    "timeline_summary",
    "evidence_bundle",
    "integrity_report",
    "reconstruction_report",
    "snapshot_seal",
    "summary",
)

FORENSIC_SNAPSHOT_REQUIRED_FIELDS: Tuple[str, ...] = (
    "stack_version",
    "report_id",
    "reconstruction_report",
    "forensic_snapshot",
    "snapshot_seal",
    "seal_metadata",
    "summary",
)

FORENSIC_COMPARISON_REQUIRED_FIELDS: Tuple[str, ...] = (
    "stack_version",
    "baseline_report_id",
    "candidate_report_id",
    "seal_comparison",
    "diff_summary",
    "diff_by_repair_chain_id",
    "seal_by_repair_chain_id",
    "seal_mismatch",
)

FORENSIC_SUMMARY_REQUIRED_FIELDS: Tuple[str, ...] = (
    "stack_version",
    "report_id",
    "session_count",
    "replay_count",
    "repair_chain_count",
    "orphan_session_count",
    "replay_divergence_count",
    "chain_break_count",
    "snapshot_seal_id",
    "repair_chain_ids",
    "source_record_count",
)

SEAL_METADATA_REQUIRED_FIELDS: Tuple[str, ...] = (
    "snapshot_seal_id",
    "report_id",
    "repair_chain_ids",
    "source_record_count",
    "seal_version",
    "hashes",
)


def forensic_report_required_fields() -> List[str]:
    return list(FORENSIC_REPORT_REQUIRED_FIELDS)


def forensic_snapshot_required_fields() -> List[str]:
    return list(FORENSIC_SNAPSHOT_REQUIRED_FIELDS)


def forensic_comparison_required_fields() -> List[str]:
    return list(FORENSIC_COMPARISON_REQUIRED_FIELDS)


def forensic_summary_required_fields() -> List[str]:
    return list(FORENSIC_SUMMARY_REQUIRED_FIELDS)


def seal_metadata_required_fields() -> List[str]:
    return list(SEAL_METADATA_REQUIRED_FIELDS)


def validate_forensic_report_contract(value: Any) -> Dict[str, Any]:
    return _validate_required_fields(
        value,
        contract_name="runtime_forensic_report.v1",
        required_fields=FORENSIC_REPORT_REQUIRED_FIELDS,
    )


def validate_forensic_snapshot_contract(value: Any) -> Dict[str, Any]:
    return _validate_required_fields(
        value,
        contract_name="runtime_forensic_snapshot.v1",
        required_fields=FORENSIC_SNAPSHOT_REQUIRED_FIELDS,
    )


def validate_forensic_comparison_contract(value: Any) -> Dict[str, Any]:
    return _validate_required_fields(
        value,
        contract_name="runtime_forensic_comparison.v1",
        required_fields=FORENSIC_COMPARISON_REQUIRED_FIELDS,
    )


def validate_forensic_summary_contract(value: Any) -> Dict[str, Any]:
    return _validate_required_fields(
        value,
        contract_name="runtime_forensic_summary.v1",
        required_fields=FORENSIC_SUMMARY_REQUIRED_FIELDS,
    )


def validate_seal_metadata_contract(value: Any) -> Dict[str, Any]:
    return _validate_required_fields(
        value,
        contract_name="runtime_forensic_seal_metadata.v1",
        required_fields=SEAL_METADATA_REQUIRED_FIELDS,
    )


def validate_runtime_forensic_stack_contracts(
    *,
    report: Any | None = None,
    snapshot: Any | None = None,
    comparison: Any | None = None,
    summary: Any | None = None,
    seal_metadata: Any | None = None,
) -> Dict[str, Any]:
    validations = {
        "report": validate_forensic_report_contract(report) if report is not None else _skipped("runtime_forensic_report.v1"),
        "snapshot": validate_forensic_snapshot_contract(snapshot) if snapshot is not None else _skipped("runtime_forensic_snapshot.v1"),
        "comparison": validate_forensic_comparison_contract(comparison) if comparison is not None else _skipped("runtime_forensic_comparison.v1"),
        "summary": validate_forensic_summary_contract(summary) if summary is not None else _skipped("runtime_forensic_summary.v1"),
        "seal_metadata": validate_seal_metadata_contract(seal_metadata) if seal_metadata is not None else _skipped("runtime_forensic_seal_metadata.v1"),
    }
    active = [item for item in validations.values() if not item.get("skipped")]
    return {
        "ok": all(item.get("ok") for item in active),
        "validations": validations,
    }


def _validate_required_fields(
    value: Any,
    *,
    contract_name: str,
    required_fields: Iterable[str],
) -> Dict[str, Any]:
    required = list(required_fields)
    if not isinstance(value, dict):
        return {
            "ok": False,
            "contract": contract_name,
            "required_fields": required,
            "missing_fields": required,
            "unexpected_type": type(value).__name__,
        }

    missing = [
        field
        for field in required
        if field not in value
    ]
    return {
        "ok": not missing,
        "contract": contract_name,
        "required_fields": required,
        "missing_fields": missing,
        "unexpected_type": "",
    }


def _skipped(contract_name: str) -> Dict[str, Any]:
    return {
        "ok": True,
        "contract": contract_name,
        "required_fields": [],
        "missing_fields": [],
        "unexpected_type": "",
        "skipped": True,
    }
