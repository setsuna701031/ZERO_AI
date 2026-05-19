from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List

from core.runtime.runtime_timeline_evidence_export import (
    build_runtime_timeline_evidence_bundle,
    detect_broken_timeline_chains,
    summarize_timeline_evidence_counts,
)
from core.runtime.runtime_timeline_reconstruction import reconstruct_runtime_timeline


def build_runtime_timeline_integrity_report(
    records: Iterable[Any],
    *,
    replays: Iterable[Any] | None = None,
    include_integrity_score: bool = True,
) -> Dict[str, Any]:
    """Return a read-only integrity report for reconstructed runtime timelines."""

    source_records = list(records)
    timeline = reconstruct_runtime_timeline(source_records, replays=replays)
    evidence_bundle = build_runtime_timeline_evidence_bundle(source_records, replays=replays)
    report = analyze_runtime_timeline_evidence(
        evidence_bundle,
        include_integrity_score=include_integrity_score,
    )
    report["source_record_count"] = len(source_records)
    report["timeline_entry_count"] = len(timeline)
    return report


def analyze_runtime_timeline_evidence(
    evidence: Any,
    *,
    include_integrity_score: bool = True,
) -> Dict[str, Any]:
    entries = _timeline_entries(evidence)
    broken_parent_refs = detect_impossible_parent_session_refs(entries)
    circular_chain_refs = detect_circular_parent_linkage(entries)
    replay_divergence = detect_replay_divergence_chains(entries)
    depth_anomalies = detect_execution_chain_depth_anomalies(entries)
    orphan_sessions = detect_orphan_sessions(entries)
    broken_chains = detect_broken_timeline_chains(entries)
    affected_repair_chain_ids = _affected_repair_chain_ids(
        [
            *orphan_sessions,
            *broken_parent_refs,
            *circular_chain_refs,
            *replay_divergence,
            *depth_anomalies,
        ],
        entries,
    )

    report = {
        "orphan_session_count": len(orphan_sessions),
        "orphan_sessions": orphan_sessions,
        "broken_parent_refs": broken_parent_refs,
        "circular_chain_refs": circular_chain_refs,
        "replay_divergence_count": len(replay_divergence),
        "replay_divergence_chains": replay_divergence,
        "replay_divergence_hints": generate_replay_divergence_hints(replay_divergence),
        "depth_anomaly_count": len(depth_anomalies),
        "depth_anomalies": depth_anomalies,
        "chain_break_count": _safe_int(broken_chains.get("chain_break_count"))
        + len(circular_chain_refs)
        + len(depth_anomalies),
        "affected_repair_chain_ids": affected_repair_chain_ids,
        "summary_counts": summarize_runtime_timeline_integrity_counts(entries),
    }
    if include_integrity_score:
        report["integrity_score"] = _integrity_score(report, len(entries))
    return report


def detect_orphan_sessions(evidence: Any) -> List[Dict[str, Any]]:
    entries = _canonical_session_entries(evidence)
    orphans: List[Dict[str, Any]] = []
    for entry in entries:
        session_id = _text(entry.get("session_id"))
        parent_session_id = _text(entry.get("parent_session_id"))
        depth = _safe_int(entry.get("execution_chain_depth"))
        if session_id and not parent_session_id and depth > 0:
            orphans.append(
                {
                    "session_id": session_id,
                    "execution_chain_depth": depth,
                    "repair_chain_id": _text(entry.get("repair_chain_id")),
                    "reason": "non_root_session_missing_parent",
                }
            )
    return orphans


def detect_impossible_parent_session_refs(evidence: Any) -> List[Dict[str, Any]]:
    entries = _canonical_session_entries(evidence)
    session_ids = {_text(entry.get("session_id")) for entry in entries if _text(entry.get("session_id"))}
    broken: List[Dict[str, Any]] = []
    for entry in entries:
        session_id = _text(entry.get("session_id"))
        parent_session_id = _text(entry.get("parent_session_id"))
        if parent_session_id and parent_session_id not in session_ids:
            broken.append(
                {
                    "session_id": session_id,
                    "parent_session_id": parent_session_id,
                    "repair_chain_id": _text(entry.get("repair_chain_id")),
                    "reason": "parent_session_id_not_found",
                }
            )
        if parent_session_id and parent_session_id == session_id:
            broken.append(
                {
                    "session_id": session_id,
                    "parent_session_id": parent_session_id,
                    "repair_chain_id": _text(entry.get("repair_chain_id")),
                    "reason": "self_parent_reference",
                }
            )
    return broken


def detect_circular_parent_linkage(evidence: Any) -> List[Dict[str, Any]]:
    entries = _canonical_session_entries(evidence)
    parents = {
        _text(entry.get("session_id")): _text(entry.get("parent_session_id"))
        for entry in entries
        if _text(entry.get("session_id"))
    }
    repair_ids = {
        _text(entry.get("session_id")): _text(entry.get("repair_chain_id"))
        for entry in entries
        if _text(entry.get("session_id"))
    }
    cycles: Dict[str, Dict[str, Any]] = {}

    for session_id in sorted(parents):
        path: List[str] = []
        seen: Dict[str, int] = {}
        current = session_id
        while current:
            if current in seen:
                cycle = path[seen[current]:]
                key = " -> ".join(sorted(cycle))
                cycles[key] = {
                    "session_ids": sorted(cycle),
                    "repair_chain_ids": sorted(
                        {
                            repair_ids.get(item, "")
                            for item in cycle
                            if repair_ids.get(item, "")
                        }
                    ),
                    "reason": "circular_parent_linkage",
                }
                break
            if current not in parents:
                break
            seen[current] = len(path)
            path.append(current)
            current = parents.get(current, "")

    return [copy.deepcopy(cycles[key]) for key in sorted(cycles)]


def detect_replay_divergence_chains(evidence: Any) -> List[Dict[str, Any]]:
    entries = _timeline_entries(evidence)
    by_replay: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        replay_id = _text(entry.get("replay_id"))
        if not replay_id:
            continue
        group = by_replay.setdefault(
            replay_id,
            {
                "replay_id": replay_id,
                "session_ids": [],
                "repair_chain_ids": [],
                "depths": [],
                "statuses": [],
                "event_types": [],
            },
        )
        for key, value in (
            ("session_ids", _text(entry.get("session_id"))),
            ("repair_chain_ids", _text(entry.get("repair_chain_id"))),
            ("statuses", _text(entry.get("status"))),
            ("event_types", _text(entry.get("event_type"))),
        ):
            if value and value not in group[key]:
                group[key].append(value)
        depth = _safe_int(entry.get("execution_chain_depth"))
        if depth not in group["depths"]:
            group["depths"].append(depth)

    divergent: List[Dict[str, Any]] = []
    for replay_id in sorted(by_replay):
        group = by_replay[replay_id]
        reasons: List[str] = []
        if len(group["repair_chain_ids"]) > 1:
            reasons.append("multiple_repair_chains_in_replay")
        if len(group["depths"]) > 1:
            reasons.append("multiple_execution_depths_in_replay")
        if group["event_types"] == ["session_continuity"]:
            reasons.append("replay_id_without_replay_records")
        if reasons:
            divergent.append(
                {
                    "replay_id": replay_id,
                    "session_ids": sorted(group["session_ids"]),
                    "repair_chain_ids": sorted(group["repair_chain_ids"]),
                    "execution_chain_depths": sorted(group["depths"]),
                    "statuses": sorted(group["statuses"]),
                    "reasons": reasons,
                }
            )
    return divergent


def detect_execution_chain_depth_anomalies(evidence: Any) -> List[Dict[str, Any]]:
    entries = _canonical_session_entries(evidence)
    by_session = {_text(entry.get("session_id")): entry for entry in entries if _text(entry.get("session_id"))}
    anomalies: List[Dict[str, Any]] = []
    for session_id in sorted(by_session):
        entry = by_session[session_id]
        parent_session_id = _text(entry.get("parent_session_id"))
        depth = _safe_int(entry.get("execution_chain_depth"))
        if not parent_session_id and depth != 0:
            anomalies.append(
                {
                    "session_id": session_id,
                    "parent_session_id": "",
                    "execution_chain_depth": depth,
                    "expected_execution_chain_depth": 0,
                    "repair_chain_id": _text(entry.get("repair_chain_id")),
                    "reason": "root_depth_must_be_zero",
                }
            )
            continue
        if parent_session_id in by_session:
            parent_depth = _safe_int(by_session[parent_session_id].get("execution_chain_depth"))
            expected = parent_depth + 1
            if depth != expected:
                anomalies.append(
                    {
                        "session_id": session_id,
                        "parent_session_id": parent_session_id,
                        "execution_chain_depth": depth,
                        "expected_execution_chain_depth": expected,
                        "repair_chain_id": _text(entry.get("repair_chain_id")),
                        "reason": "child_depth_must_follow_parent_depth",
                    }
                )
    return anomalies


def summarize_runtime_timeline_integrity_counts(evidence: Any) -> Dict[str, Any]:
    entries = _timeline_entries(evidence)
    evidence_counts = summarize_timeline_evidence_counts(entries)
    return {
        "timeline_entry_count": evidence_counts["timeline_entry_count"],
        "source_record_count": evidence_counts["source_record_count"],
        "session_count": evidence_counts["session_count"],
        "replay_count": evidence_counts["replay_count"],
        "repair_chain_count": evidence_counts["repair_chain_count"],
        "orphan_session_count": len(detect_orphan_sessions(entries)),
        "broken_parent_ref_count": len(detect_impossible_parent_session_refs(entries)),
        "circular_chain_ref_count": len(detect_circular_parent_linkage(entries)),
        "replay_divergence_count": len(detect_replay_divergence_chains(entries)),
        "depth_anomaly_count": len(detect_execution_chain_depth_anomalies(entries)),
        "chain_break_count": evidence_counts["chain_break_count"],
    }


def generate_replay_divergence_hints(divergence_chains: Iterable[Any]) -> List[Dict[str, Any]]:
    hints: List[Dict[str, Any]] = []
    for item in divergence_chains:
        payload = item if isinstance(item, dict) else {}
        replay_id = _text(payload.get("replay_id"))
        if not replay_id:
            continue
        reasons = [
            _text(reason)
            for reason in payload.get("reasons", [])
            if _text(reason)
        ]
        hints.append(
            {
                "replay_id": replay_id,
                "hint": "review replay lineage before trusting reconstructed replay evidence",
                "reasons": reasons,
                "affected_sessions": list(payload.get("session_ids") or []),
            }
        )
    return hints


def _canonical_session_entries(evidence: Any) -> List[Dict[str, Any]]:
    entries = _timeline_entries(evidence)
    by_session: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        session_id = _text(entry.get("session_id"))
        if not session_id:
            continue
        if session_id not in by_session or _text(entry.get("event_type")) == "session_continuity":
            by_session[session_id] = copy.deepcopy(entry)
    return [copy.deepcopy(by_session[key]) for key in sorted(by_session)]


def _timeline_entries(evidence: Any) -> List[Dict[str, Any]]:
    if isinstance(evidence, dict):
        entries = evidence.get("timeline")
    else:
        entries = evidence
    if not isinstance(entries, list):
        return []
    return [copy.deepcopy(entry) for entry in entries if isinstance(entry, dict)]


def _affected_repair_chain_ids(findings: Iterable[Any], entries: List[Dict[str, Any]]) -> List[str]:
    affected = {
        _text(item.get("repair_chain_id"))
        for item in findings
        if isinstance(item, dict) and _text(item.get("repair_chain_id"))
    }
    affected_sessions = {
        _text(item.get("session_id"))
        for item in findings
        if isinstance(item, dict) and _text(item.get("session_id"))
    }
    for item in findings:
        if isinstance(item, dict):
            affected_sessions.update(
                _text(session_id)
                for session_id in item.get("session_ids", [])
                if _text(session_id)
            )
    for entry in entries:
        if _text(entry.get("session_id")) in affected_sessions and _text(entry.get("repair_chain_id")):
            affected.add(_text(entry.get("repair_chain_id")))
    return sorted(affected)


def _integrity_score(report: Dict[str, Any], entry_count: int) -> int:
    if entry_count <= 0:
        return 100
    penalties = (
        report["orphan_session_count"]
        + len(report["broken_parent_refs"])
        + len(report["circular_chain_refs"])
        + report["replay_divergence_count"]
        + report["depth_anomaly_count"]
        + report["chain_break_count"]
    )
    return max(0, 100 - int((penalties / max(1, entry_count)) * 100))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0
