from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List

from core.runtime.runtime_replay_diff_comparator import (
    compare_replay_reconstruction_reports,
    generate_stable_diff_summary,
    group_replay_diffs_by_repair_chain_id,
)
from core.runtime.runtime_replay_reconstruction_report import (
    build_runtime_replay_reconstruction_report,
    generate_replay_reconstruction_forensic_snapshot,
    summarize_replay_reconstruction_report,
)
from core.runtime.runtime_replay_snapshot_seal import (
    compare_replay_snapshot_seals,
    generate_replay_snapshot_seal_metadata,
    group_replay_snapshot_seals_by_repair_chain_id,
    seal_replay_reconstruction_report,
)
from core.runtime.runtime_timeline_evidence_export import (
    build_runtime_timeline_evidence_bundle,
    summarize_timeline_evidence_counts,
)
from core.runtime.runtime_timeline_integrity_analyzer import (
    analyze_runtime_timeline_evidence,
)
from core.runtime.runtime_timeline_reconstruction import (
    build_runtime_timeline_summary,
    reconstruct_runtime_timeline,
)


STACK_VERSION = "runtime_forensic_stack.v1"


def build_runtime_forensic_report(
    records: Iterable[Any],
    *,
    replays: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    """Build a read-only forensic stack report by composing runtime helpers."""

    source_records = list(records)
    timeline_entries = reconstruct_runtime_timeline(source_records, replays=replays)
    timeline_summary = build_runtime_timeline_summary(source_records, replays=replays)
    evidence_bundle = build_runtime_timeline_evidence_bundle(source_records, replays=replays)
    integrity_report = analyze_runtime_timeline_evidence(evidence_bundle)
    reconstruction_report = build_runtime_replay_reconstruction_report(source_records, replays=replays)
    snapshot_seal = seal_replay_reconstruction_report(reconstruction_report)
    return {
        "stack_version": STACK_VERSION,
        "report_id": reconstruction_report["report_id"],
        "timeline_entries": copy.deepcopy(timeline_entries),
        "timeline_summary": copy.deepcopy(timeline_summary),
        "evidence_bundle": copy.deepcopy(evidence_bundle),
        "integrity_report": copy.deepcopy(integrity_report),
        "reconstruction_report": copy.deepcopy(reconstruction_report),
        "snapshot_seal": copy.deepcopy(snapshot_seal),
        "summary": summarize_runtime_forensic_stack(
            {
                "reconstruction_report": reconstruction_report,
                "snapshot_seal": snapshot_seal,
                "evidence_bundle": evidence_bundle,
            }
        ),
    }


def build_runtime_forensic_snapshot(
    records: Iterable[Any],
    *,
    replays: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    """Build a stable forensic snapshot and seal from runtime records."""

    stack_report = build_runtime_forensic_report(records, replays=replays)
    reconstruction_report = stack_report["reconstruction_report"]
    forensic_snapshot = generate_replay_reconstruction_forensic_snapshot(reconstruction_report)
    seal_metadata = generate_replay_snapshot_seal_metadata(stack_report["snapshot_seal"])
    return {
        "stack_version": STACK_VERSION,
        "report_id": stack_report["report_id"],
        "reconstruction_report": copy.deepcopy(reconstruction_report),
        "forensic_snapshot": forensic_snapshot,
        "snapshot_seal": copy.deepcopy(stack_report["snapshot_seal"]),
        "seal_metadata": seal_metadata,
        "summary": summarize_runtime_forensic_stack(stack_report),
    }


def compare_runtime_forensic_snapshots(
    baseline_snapshot: Any,
    candidate_snapshot: Any,
) -> Dict[str, Any]:
    """Compare two forensic snapshots using existing report and seal comparators."""

    baseline = _mapping(baseline_snapshot)
    candidate = _mapping(candidate_snapshot)
    baseline_report = _extract_reconstruction_report(baseline)
    candidate_report = _extract_reconstruction_report(candidate)
    diff = (
        compare_replay_reconstruction_reports(baseline_report, candidate_report)
        if baseline_report and candidate_report
        else {}
    )
    seal_comparison = compare_replay_snapshot_seals(
        baseline.get("snapshot_seal", {}),
        candidate.get("snapshot_seal", {}),
    )
    return {
        "stack_version": STACK_VERSION,
        "baseline_report_id": _text(baseline.get("report_id")),
        "candidate_report_id": _text(candidate.get("report_id")),
        "seal_comparison": seal_comparison,
        "diff_summary": generate_stable_diff_summary(diff) if diff else {},
        "diff_by_repair_chain_id": group_replay_diffs_by_repair_chain_id([diff]) if diff else [],
        "seal_by_repair_chain_id": group_replay_snapshot_seals_by_repair_chain_id(
            [
                baseline.get("snapshot_seal", {}),
                candidate.get("snapshot_seal", {}),
            ]
        ),
        "seal_mismatch": bool(seal_comparison.get("seal_mismatch")),
    }


def summarize_runtime_forensic_stack(stack: Any) -> Dict[str, Any]:
    """Return a lightweight summary for a forensic stack report or snapshot."""

    payload = _mapping(stack)
    reconstruction_report = _extract_reconstruction_report(payload)
    evidence_bundle = _extract_evidence_bundle(payload, reconstruction_report)
    seal = payload.get("snapshot_seal") if isinstance(payload.get("snapshot_seal"), dict) else {}
    report_summary = summarize_replay_reconstruction_report(reconstruction_report)
    evidence_counts = summarize_timeline_evidence_counts(evidence_bundle)
    return {
        "stack_version": _text(payload.get("stack_version")) or STACK_VERSION,
        "report_id": _text(payload.get("report_id") or reconstruction_report.get("report_id")),
        "session_count": _safe_int(report_summary.get("session_count") or evidence_counts.get("session_count")),
        "replay_count": _safe_int(report_summary.get("replay_count") or evidence_counts.get("replay_count")),
        "repair_chain_count": _safe_int(report_summary.get("repair_chain_count") or evidence_counts.get("repair_chain_count")),
        "orphan_session_count": _safe_int(report_summary.get("orphan_session_count")),
        "replay_divergence_count": _safe_int(report_summary.get("replay_divergence_count")),
        "chain_break_count": _safe_int(report_summary.get("chain_break_count")),
        "snapshot_seal_id": _text(seal.get("snapshot_seal_id")),
        "repair_chain_ids": copy.deepcopy(seal.get("repair_chain_ids", [])),
        "source_record_count": _safe_int(seal.get("source_record_count") or evidence_counts.get("source_record_count")),
    }


def _extract_reconstruction_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(payload.get("reconstruction_report"), dict):
        return copy.deepcopy(payload["reconstruction_report"])
    if isinstance(payload.get("report"), dict):
        return copy.deepcopy(payload["report"])
    if isinstance(payload.get("forensic_snapshot"), dict):
        snapshot = payload["forensic_snapshot"]
        return {
            "report_id": _text(snapshot.get("report_id")),
            "integrity_summary": copy.deepcopy(snapshot.get("integrity_summary", {})),
            "chain_break_summary": copy.deepcopy(snapshot.get("chain_break_summary", {})),
            "affected_repair_chain_ids": copy.deepcopy(snapshot.get("affected_repair_chain_ids", [])),
        }
    return {}


def _extract_evidence_bundle(
    payload: Dict[str, Any],
    reconstruction_report: Dict[str, Any],
) -> Dict[str, Any]:
    if isinstance(payload.get("evidence_bundle"), dict):
        return copy.deepcopy(payload["evidence_bundle"])
    if isinstance(reconstruction_report.get("evidence_bundle"), dict):
        return copy.deepcopy(reconstruction_report["evidence_bundle"])
    return {}


def _mapping(value: Any) -> Dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0
