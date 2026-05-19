from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List

from core.runtime.runtime_timeline_evidence_export import (
    build_runtime_timeline_evidence_bundle,
    group_timeline_evidence_by_repair_chain_id,
    summarize_timeline_evidence_counts,
)
from core.runtime.runtime_timeline_integrity_analyzer import (
    analyze_runtime_timeline_evidence,
)
from core.runtime.runtime_timeline_reconstruction import reconstruct_runtime_timeline


SCHEMA_VERSION = "runtime_replay_reconstruction_report.v1"


def build_runtime_replay_reconstruction_report(
    records: Iterable[Any],
    *,
    replays: Iterable[Any] | None = None,
    include_integrity_score: bool = True,
) -> Dict[str, Any]:
    """Build a stable, read-only replay reconstruction report."""

    source_records = list(records)
    timeline_entries = reconstruct_runtime_timeline(source_records, replays=replays)
    evidence_bundle = build_runtime_timeline_evidence_bundle(source_records, replays=replays)
    analyzer_results = analyze_runtime_timeline_evidence(
        evidence_bundle,
        include_integrity_score=include_integrity_score,
    )
    counts = summarize_timeline_evidence_counts(evidence_bundle)
    integrity_summary = _integrity_summary(analyzer_results, counts)
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_id": _report_id(evidence_bundle),
        "session_count": counts["session_count"],
        "replay_count": counts["replay_count"],
        "repair_chain_count": counts["repair_chain_count"],
        "orphan_session_count": analyzer_results["orphan_session_count"],
        "replay_divergence_count": analyzer_results["replay_divergence_count"],
        "chain_break_count": analyzer_results["chain_break_count"],
        "integrity_summary": integrity_summary,
        "replay_divergence_hints": copy.deepcopy(analyzer_results.get("replay_divergence_hints", [])),
        "chain_break_summary": _chain_break_summary(evidence_bundle, analyzer_results),
        "timeline_entries": copy.deepcopy(timeline_entries),
        "evidence_bundle": copy.deepcopy(evidence_bundle),
        "analyzer_results": copy.deepcopy(analyzer_results),
        "affected_repair_chain_ids": copy.deepcopy(analyzer_results.get("affected_repair_chain_ids", [])),
    }
    return report


def group_replay_reconstruction_reports_by_repair_chain_id(
    reports: Iterable[Any],
) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for report in reports:
        payload = report if isinstance(report, dict) else {}
        report_id = _text(payload.get("report_id"))
        affected = payload.get("affected_repair_chain_ids")
        repair_chain_ids = [
            _text(item)
            for item in affected
            if _text(item)
        ] if isinstance(affected, list) else []
        if not repair_chain_ids:
            evidence_groups = group_timeline_evidence_by_repair_chain_id(payload.get("evidence_bundle", {}))
            repair_chain_ids = [
                _text(item.get("repair_chain_id"))
                for item in evidence_groups
                if _text(item.get("repair_chain_id"))
            ]

        for repair_chain_id in sorted(set(repair_chain_ids)):
            group = groups.setdefault(
                repair_chain_id,
                {
                    "repair_chain_id": repair_chain_id,
                    "report_ids": [],
                    "reports": [],
                    "chain_break_count": 0,
                    "replay_divergence_count": 0,
                    "orphan_session_count": 0,
                },
            )
            if report_id and report_id not in group["report_ids"]:
                group["report_ids"].append(report_id)
            group["reports"].append(_lightweight_report_view(payload))
            group["chain_break_count"] += _safe_int(payload.get("chain_break_count"))
            group["replay_divergence_count"] += _safe_int(payload.get("replay_divergence_count"))
            group["orphan_session_count"] += _safe_int(payload.get("orphan_session_count"))

    return [copy.deepcopy(groups[key]) for key in sorted(groups)]


def generate_replay_reconstruction_forensic_snapshot(report: Any) -> Dict[str, Any]:
    payload = report if isinstance(report, dict) else {}
    analyzer = payload.get("analyzer_results") if isinstance(payload.get("analyzer_results"), dict) else {}
    evidence = payload.get("evidence_bundle") if isinstance(payload.get("evidence_bundle"), dict) else {}
    return {
        "schema_version": "runtime_replay_reconstruction_forensic_snapshot.v1",
        "report_id": _text(payload.get("report_id")),
        "integrity_summary": copy.deepcopy(payload.get("integrity_summary", {})),
        "chain_break_summary": copy.deepcopy(payload.get("chain_break_summary", {})),
        "affected_repair_chain_ids": copy.deepcopy(payload.get("affected_repair_chain_ids", [])),
        "replay_divergence_hints": copy.deepcopy(payload.get("replay_divergence_hints", [])),
        "broken_parent_refs": copy.deepcopy(analyzer.get("broken_parent_refs", [])),
        "circular_chain_refs": copy.deepcopy(analyzer.get("circular_chain_refs", [])),
        "depth_anomalies": copy.deepcopy(analyzer.get("depth_anomalies", [])),
        "timeline_entry_count": _safe_int(evidence.get("timeline_entry_count")),
        "source_record_count": _safe_int(evidence.get("source_record_count")),
        "snapshot_hash": _stable_hash(
            {
                "report_id": _text(payload.get("report_id")),
                "integrity_summary": payload.get("integrity_summary", {}),
                "chain_break_summary": payload.get("chain_break_summary", {}),
                "affected_repair_chain_ids": payload.get("affected_repair_chain_ids", []),
            }
        ),
    }


def summarize_replay_reconstruction_report(report: Any) -> Dict[str, Any]:
    payload = report if isinstance(report, dict) else {}
    return _lightweight_report_view(payload)


def summarize_replay_reconstruction_reports(reports: Iterable[Any]) -> Dict[str, Any]:
    items = [report for report in reports if isinstance(report, dict)]
    repair_chain_ids = {
        _text(chain_id)
        for report in items
        for chain_id in report.get("affected_repair_chain_ids", [])
        if _text(chain_id)
    }
    return {
        "report_count": len(items),
        "session_count": sum(_safe_int(item.get("session_count")) for item in items),
        "replay_count": sum(_safe_int(item.get("replay_count")) for item in items),
        "repair_chain_count": len(repair_chain_ids),
        "orphan_session_count": sum(_safe_int(item.get("orphan_session_count")) for item in items),
        "replay_divergence_count": sum(_safe_int(item.get("replay_divergence_count")) for item in items),
        "chain_break_count": sum(_safe_int(item.get("chain_break_count")) for item in items),
        "affected_repair_chain_ids": sorted(repair_chain_ids),
    }


def _integrity_summary(analyzer_results: Dict[str, Any], counts: Dict[str, Any]) -> Dict[str, Any]:
    summary = {
        "timeline_entry_count": counts["timeline_entry_count"],
        "source_record_count": counts["source_record_count"],
        "session_count": counts["session_count"],
        "replay_count": counts["replay_count"],
        "repair_chain_count": counts["repair_chain_count"],
        "orphan_session_count": analyzer_results["orphan_session_count"],
        "broken_parent_ref_count": len(analyzer_results.get("broken_parent_refs", [])),
        "circular_chain_ref_count": len(analyzer_results.get("circular_chain_refs", [])),
        "replay_divergence_count": analyzer_results["replay_divergence_count"],
        "depth_anomaly_count": analyzer_results["depth_anomaly_count"],
        "chain_break_count": analyzer_results["chain_break_count"],
    }
    if "integrity_score" in analyzer_results:
        summary["integrity_score"] = analyzer_results["integrity_score"]
    return summary


def _chain_break_summary(evidence_bundle: Dict[str, Any], analyzer_results: Dict[str, Any]) -> Dict[str, Any]:
    broken = evidence_bundle.get("broken_timeline_chains") if isinstance(evidence_bundle.get("broken_timeline_chains"), dict) else {}
    return {
        "chain_break_count": analyzer_results["chain_break_count"],
        "missing_parent_ref_count": len(broken.get("missing_parent_refs") or []),
        "missing_previous_runtime_ref_count": len(broken.get("missing_previous_runtime_refs") or []),
        "circular_chain_ref_count": len(analyzer_results.get("circular_chain_refs", [])),
        "depth_anomaly_count": analyzer_results["depth_anomaly_count"],
    }


def _lightweight_report_view(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "report_id": _text(report.get("report_id")),
        "session_count": _safe_int(report.get("session_count")),
        "replay_count": _safe_int(report.get("replay_count")),
        "repair_chain_count": _safe_int(report.get("repair_chain_count")),
        "orphan_session_count": _safe_int(report.get("orphan_session_count")),
        "replay_divergence_count": _safe_int(report.get("replay_divergence_count")),
        "chain_break_count": _safe_int(report.get("chain_break_count")),
        "affected_repair_chain_ids": copy.deepcopy(report.get("affected_repair_chain_ids", [])),
    }


def _report_id(evidence_bundle: Dict[str, Any]) -> str:
    return "replay-reconstruction-" + _stable_hash(evidence_bundle)[:16]


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0
