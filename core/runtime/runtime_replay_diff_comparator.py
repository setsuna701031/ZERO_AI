from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List

from core.runtime.runtime_replay_reconstruction_report import (
    summarize_replay_reconstruction_report,
)
from core.runtime.runtime_timeline_evidence_export import (
    detect_broken_timeline_chains,
    summarize_timeline_evidence_counts,
)
from core.runtime.runtime_timeline_integrity_analyzer import (
    analyze_runtime_timeline_evidence,
)


SCHEMA_VERSION = "runtime_replay_diff_comparator.v1"


def compare_replay_reconstruction_reports(
    baseline_report: Any,
    candidate_report: Any,
) -> Dict[str, Any]:
    """Compare two replay reconstruction reports without mutating either input."""

    baseline = _report_mapping(baseline_report)
    candidate = _report_mapping(candidate_report)
    divergence_regions = detect_replay_divergence_regions(baseline, candidate)
    replay_drift = detect_replay_drift(baseline, candidate)
    integrity_delta = compare_integrity_summaries(baseline, candidate)
    new_orphans = detect_newly_introduced_orphan_sessions(baseline, candidate)
    chain_break_delta = compare_chain_break_deltas(baseline, candidate)
    affected_repair_chain_ids = _affected_repair_chain_ids(
        baseline,
        candidate,
        divergence_regions,
        replay_drift,
        new_orphans,
        chain_break_delta,
    )
    severity = generate_divergence_severity_hints(
        divergence_count=len(divergence_regions),
        replay_drift_count=len(replay_drift),
        new_orphan_count=len(new_orphans),
        new_chain_break_count=len(chain_break_delta["new_chain_breaks"]),
        integrity_delta=integrity_delta,
    )
    comparison = {
        "schema_version": SCHEMA_VERSION,
        "comparison_id": _comparison_id(baseline, candidate),
        "baseline_report_id": _text(baseline.get("report_id")),
        "candidate_report_id": _text(candidate.get("report_id")),
        "divergence_count": len(divergence_regions),
        "divergence_regions": divergence_regions,
        "replay_drift_count": len(replay_drift),
        "replay_drift": replay_drift,
        "integrity_delta": integrity_delta,
        "new_orphan_sessions": new_orphans,
        "new_chain_breaks": chain_break_delta["new_chain_breaks"],
        "chain_break_delta": chain_break_delta,
        "affected_repair_chain_ids": affected_repair_chain_ids,
        "severity_hint": severity,
    }
    comparison["summary"] = generate_stable_diff_summary(comparison)
    return comparison


def detect_replay_divergence_regions(
    baseline_report: Any,
    candidate_report: Any,
) -> List[Dict[str, Any]]:
    baseline = _report_mapping(baseline_report)
    candidate = _report_mapping(candidate_report)
    baseline_divergence = {
        _divergence_signature(item)
        for item in _analyzer_list(baseline, "replay_divergence_chains")
    }
    regions: List[Dict[str, Any]] = []
    for item in _analyzer_list(candidate, "replay_divergence_chains"):
        signature = _divergence_signature(item)
        if signature not in baseline_divergence:
            regions.append(
                {
                    "replay_id": _text(item.get("replay_id")),
                    "session_ids": copy.deepcopy(item.get("session_ids", [])),
                    "repair_chain_ids": copy.deepcopy(item.get("repair_chain_ids", [])),
                    "execution_chain_depths": copy.deepcopy(item.get("execution_chain_depths", [])),
                    "reasons": copy.deepcopy(item.get("reasons", [])),
                }
            )
    return sorted(regions, key=lambda item: item["replay_id"])


def compare_chain_break_deltas(
    baseline_report: Any,
    candidate_report: Any,
) -> Dict[str, Any]:
    baseline = _report_mapping(baseline_report)
    candidate = _report_mapping(candidate_report)
    baseline_breaks = _chain_break_signatures(baseline)
    candidate_breaks = _chain_break_signatures(candidate)
    new_breaks = [
        _chain_break_from_signature(signature)
        for signature in sorted(candidate_breaks - baseline_breaks)
    ]
    resolved_breaks = [
        _chain_break_from_signature(signature)
        for signature in sorted(baseline_breaks - candidate_breaks)
    ]
    baseline_count = _safe_int(baseline.get("chain_break_count"))
    candidate_count = _safe_int(candidate.get("chain_break_count"))
    return {
        "baseline_chain_break_count": baseline_count,
        "candidate_chain_break_count": candidate_count,
        "delta": candidate_count - baseline_count,
        "new_chain_breaks": new_breaks,
        "resolved_chain_breaks": resolved_breaks,
    }


def compare_integrity_summaries(
    baseline_report: Any,
    candidate_report: Any,
) -> Dict[str, Any]:
    baseline = _summary_mapping(_report_mapping(baseline_report))
    candidate = _summary_mapping(_report_mapping(candidate_report))
    keys = sorted(set(baseline) | set(candidate))
    deltas: Dict[str, Dict[str, int]] = {}
    for key in keys:
        base = _safe_int(baseline.get(key))
        cand = _safe_int(candidate.get(key))
        if base != cand:
            deltas[key] = {
                "baseline": base,
                "candidate": cand,
                "delta": cand - base,
            }
    return deltas


def detect_newly_introduced_orphan_sessions(
    baseline_report: Any,
    candidate_report: Any,
) -> List[Dict[str, Any]]:
    baseline_orphans = {
        _text(item.get("session_id"))
        for item in _analyzer_list(_report_mapping(baseline_report), "orphan_sessions")
    }
    new_orphans: List[Dict[str, Any]] = []
    for item in _analyzer_list(_report_mapping(candidate_report), "orphan_sessions"):
        session_id = _text(item.get("session_id"))
        if session_id and session_id not in baseline_orphans:
            new_orphans.append(copy.deepcopy(item))
    return sorted(new_orphans, key=lambda item: _text(item.get("session_id")))


def detect_replay_drift(
    baseline_report: Any,
    candidate_report: Any,
) -> List[Dict[str, Any]]:
    baseline_entries = _entry_map(_timeline_entries(_report_mapping(baseline_report)))
    candidate_entries = _entry_map(_timeline_entries(_report_mapping(candidate_report)))
    drift: List[Dict[str, Any]] = []
    for key in sorted(set(baseline_entries) | set(candidate_entries)):
        baseline_entry = baseline_entries.get(key)
        candidate_entry = candidate_entries.get(key)
        if baseline_entry is None:
            drift.append(_drift_entry("added_timeline_entry", candidate_entry, None))
            continue
        if candidate_entry is None:
            drift.append(_drift_entry("removed_timeline_entry", baseline_entry, None))
            continue
        changed_fields = []
        for field in ("status", "repair_chain_id", "execution_chain_depth", "parent_session_id"):
            if baseline_entry.get(field) != candidate_entry.get(field):
                changed_fields.append(
                    {
                        "field": field,
                        "baseline": copy.deepcopy(baseline_entry.get(field)),
                        "candidate": copy.deepcopy(candidate_entry.get(field)),
                    }
                )
        if changed_fields:
            drift.append(_drift_entry("changed_timeline_entry", candidate_entry, changed_fields))
    return drift


def generate_stable_diff_summary(comparison: Any) -> Dict[str, Any]:
    payload = comparison if isinstance(comparison, dict) else {}
    return {
        "comparison_id": _text(payload.get("comparison_id")),
        "baseline_report_id": _text(payload.get("baseline_report_id")),
        "candidate_report_id": _text(payload.get("candidate_report_id")),
        "divergence_count": _safe_int(payload.get("divergence_count")),
        "replay_drift_count": _safe_int(payload.get("replay_drift_count")),
        "new_orphan_session_count": len(payload.get("new_orphan_sessions") or []),
        "new_chain_break_count": len(payload.get("new_chain_breaks") or []),
        "affected_repair_chain_ids": copy.deepcopy(payload.get("affected_repair_chain_ids", [])),
        "severity_hint": copy.deepcopy(payload.get("severity_hint", {})),
    }


def generate_divergence_severity_hints(
    *,
    divergence_count: int,
    replay_drift_count: int,
    new_orphan_count: int,
    new_chain_break_count: int,
    integrity_delta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    integrity_delta = integrity_delta or {}
    negative_score_delta = _safe_int(integrity_delta.get("integrity_score", {}).get("delta")) < 0
    if new_orphan_count or new_chain_break_count or negative_score_delta:
        level = "high"
    elif divergence_count or replay_drift_count:
        level = "medium"
    else:
        level = "low"
    reasons: List[str] = []
    if divergence_count:
        reasons.append("new_replay_divergence")
    if replay_drift_count:
        reasons.append("replay_drift_detected")
    if new_orphan_count:
        reasons.append("new_orphan_sessions")
    if new_chain_break_count:
        reasons.append("new_chain_breaks")
    if negative_score_delta:
        reasons.append("integrity_score_regressed")
    return {
        "level": level,
        "reasons": reasons,
    }


def group_replay_diffs_by_repair_chain_id(
    comparisons: Iterable[Any],
) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for comparison in comparisons:
        payload = comparison if isinstance(comparison, dict) else {}
        comparison_id = _text(payload.get("comparison_id"))
        for repair_chain_id in payload.get("affected_repair_chain_ids", []) or []:
            repair_chain_id = _text(repair_chain_id)
            if not repair_chain_id:
                continue
            group = groups.setdefault(
                repair_chain_id,
                {
                    "repair_chain_id": repair_chain_id,
                    "comparison_ids": [],
                    "comparisons": [],
                    "divergence_count": 0,
                    "replay_drift_count": 0,
                    "new_chain_break_count": 0,
                    "new_orphan_session_count": 0,
                },
            )
            if comparison_id and comparison_id not in group["comparison_ids"]:
                group["comparison_ids"].append(comparison_id)
            group["comparisons"].append(generate_stable_diff_summary(payload))
            group["divergence_count"] += _safe_int(payload.get("divergence_count"))
            group["replay_drift_count"] += _safe_int(payload.get("replay_drift_count"))
            group["new_chain_break_count"] += len(payload.get("new_chain_breaks") or [])
            group["new_orphan_session_count"] += len(payload.get("new_orphan_sessions") or [])
    return [copy.deepcopy(groups[key]) for key in sorted(groups)]


def _report_mapping(report: Any) -> Dict[str, Any]:
    if isinstance(report, dict):
        return copy.deepcopy(report)
    return {}


def _summary_mapping(report: Dict[str, Any]) -> Dict[str, Any]:
    summary = report.get("integrity_summary")
    if isinstance(summary, dict):
        return summary
    return summarize_replay_reconstruction_report(report)


def _analyzer_list(report: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    analyzer = report.get("analyzer_results")
    if not isinstance(analyzer, dict):
        evidence = report.get("evidence_bundle", {})
        analyzer = analyze_runtime_timeline_evidence(evidence)
    values = analyzer.get(key)
    if not isinstance(values, list):
        return []
    return [copy.deepcopy(item) for item in values if isinstance(item, dict)]


def _timeline_entries(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries = report.get("timeline_entries")
    if isinstance(entries, list):
        return [copy.deepcopy(item) for item in entries if isinstance(item, dict)]
    evidence = report.get("evidence_bundle")
    if isinstance(evidence, dict) and isinstance(evidence.get("timeline"), list):
        return [copy.deepcopy(item) for item in evidence["timeline"] if isinstance(item, dict)]
    return []


def _entry_map(entries: List[Dict[str, Any]]) -> Dict[tuple[str, str, str], Dict[str, Any]]:
    result: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    for entry in entries:
        key = (
            _text(entry.get("session_id")),
            _text(entry.get("replay_id")),
            _text(entry.get("event_type")),
        )
        result[key] = copy.deepcopy(entry)
    return result


def _drift_entry(reason: str, entry: Dict[str, Any] | None, changed_fields: Any) -> Dict[str, Any]:
    entry = entry or {}
    result = {
        "reason": reason,
        "session_id": _text(entry.get("session_id")),
        "replay_id": _text(entry.get("replay_id")),
        "repair_chain_id": _text(entry.get("repair_chain_id")),
        "event_type": _text(entry.get("event_type")),
    }
    if changed_fields is not None:
        result["changed_fields"] = copy.deepcopy(changed_fields)
    return result


def _chain_break_signatures(report: Dict[str, Any]) -> set[str]:
    evidence = report.get("evidence_bundle")
    broken = detect_broken_timeline_chains(evidence if isinstance(evidence, dict) else [])
    signatures = set()
    for item in broken.get("missing_parent_refs", []):
        signatures.add(
            "missing_parent|"
            + _text(item.get("session_id"))
            + "|"
            + _text(item.get("parent_session_id"))
            + "|"
            + _text(item.get("event_type"))
        )
    for item in broken.get("missing_previous_runtime_refs", []):
        signatures.add(
            "missing_previous|"
            + _text(item.get("session_id"))
            + "|"
            + str(_safe_int(item.get("execution_chain_depth")))
            + "|"
            + _text(item.get("event_type"))
        )
    analyzer = report.get("analyzer_results") if isinstance(report.get("analyzer_results"), dict) else {}
    for item in analyzer.get("circular_chain_refs", []) or []:
        if isinstance(item, dict):
            signatures.add("circular|" + ",".join(sorted(_text(value) for value in item.get("session_ids", []))))
    for item in analyzer.get("depth_anomalies", []) or []:
        if isinstance(item, dict):
            signatures.add(
                "depth|"
                + _text(item.get("session_id"))
                + "|"
                + _text(item.get("reason"))
            )
    return signatures


def _chain_break_from_signature(signature: str) -> Dict[str, Any]:
    parts = signature.split("|")
    kind = parts[0] if parts else ""
    result = {"kind": kind}
    if kind == "missing_parent" and len(parts) >= 4:
        result.update({"session_id": parts[1], "parent_session_id": parts[2], "event_type": parts[3]})
    elif kind == "missing_previous" and len(parts) >= 4:
        result.update({"session_id": parts[1], "execution_chain_depth": _safe_int(parts[2]), "event_type": parts[3]})
    elif kind == "circular" and len(parts) >= 2:
        result.update({"session_ids": [value for value in parts[1].split(",") if value]})
    elif kind == "depth" and len(parts) >= 3:
        result.update({"session_id": parts[1], "reason": parts[2]})
    return result


def _divergence_signature(item: Dict[str, Any]) -> str:
    return _stable_hash(
        {
            "replay_id": _text(item.get("replay_id")),
            "session_ids": sorted(_text(value) for value in item.get("session_ids", [])),
            "repair_chain_ids": sorted(_text(value) for value in item.get("repair_chain_ids", [])),
            "reasons": sorted(_text(value) for value in item.get("reasons", [])),
        }
    )


def _affected_repair_chain_ids(
    baseline: Dict[str, Any],
    candidate: Dict[str, Any],
    divergence_regions: List[Dict[str, Any]],
    replay_drift: List[Dict[str, Any]],
    new_orphans: List[Dict[str, Any]],
    chain_break_delta: Dict[str, Any],
) -> List[str]:
    affected = {
        _text(value)
        for value in candidate.get("affected_repair_chain_ids", [])
        if _text(value)
    }
    affected.update(
        _text(value)
        for value in baseline.get("affected_repair_chain_ids", [])
        if _text(value)
    )
    for region in divergence_regions:
        affected.update(_text(value) for value in region.get("repair_chain_ids", []) if _text(value))
    for item in [*replay_drift, *new_orphans]:
        if _text(item.get("repair_chain_id")):
            affected.add(_text(item.get("repair_chain_id")))
    candidate_entries = _timeline_entries(candidate)
    by_session = {
        _text(entry.get("session_id")): _text(entry.get("repair_chain_id"))
        for entry in candidate_entries
        if _text(entry.get("session_id")) and _text(entry.get("repair_chain_id"))
    }
    for item in chain_break_delta.get("new_chain_breaks", []):
        repair_chain_id = by_session.get(_text(item.get("session_id")))
        if repair_chain_id:
            affected.add(repair_chain_id)
    return sorted(affected)


def _comparison_id(baseline: Dict[str, Any], candidate: Dict[str, Any]) -> str:
    payload = {
        "baseline_report_id": _text(baseline.get("report_id")),
        "candidate_report_id": _text(candidate.get("report_id")),
        "baseline_summary": _summary_mapping(baseline),
        "candidate_summary": _summary_mapping(candidate),
    }
    return "replay-diff-" + _stable_hash(payload)[:16]


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
