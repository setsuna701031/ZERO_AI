from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List

from core.runtime.runtime_replay_diff_comparator import (
    generate_stable_diff_summary,
)
from core.runtime.runtime_replay_reconstruction_report import (
    generate_replay_reconstruction_forensic_snapshot,
    summarize_replay_reconstruction_report,
)
from core.runtime.runtime_timeline_evidence_export import (
    group_timeline_evidence_by_repair_chain_id,
    summarize_timeline_evidence_counts,
)


SEAL_VERSION = "runtime_replay_snapshot_seal.v1"


def generate_replay_snapshot_hash(value: Any) -> str:
    """Return a deterministic hash for replay snapshot evidence."""

    return _stable_hash(value)


def seal_replay_reconstruction_report(report: Any) -> Dict[str, Any]:
    payload = _mapping(report)
    evidence = payload.get("evidence_bundle") if isinstance(payload.get("evidence_bundle"), dict) else {}
    analyzer = payload.get("analyzer_results") if isinstance(payload.get("analyzer_results"), dict) else {}
    repair_chain_ids = _repair_chain_ids_for_report(payload)
    source_count = _safe_int(evidence.get("source_record_count"))
    replay_hash = generate_replay_snapshot_hash(
        {
            "report_id": _text(payload.get("report_id")),
            "timeline": evidence.get("timeline", []),
            "summary": summarize_timeline_evidence_counts(evidence),
        }
    )
    integrity_hash = generate_replay_snapshot_hash(
        {
            "integrity_summary": payload.get("integrity_summary", {}),
            "analyzer_results": analyzer,
        }
    )
    divergence_hash = generate_replay_snapshot_hash(
        {
            "replay_divergence_hints": payload.get("replay_divergence_hints", []),
            "affected_repair_chain_ids": repair_chain_ids,
        }
    )
    seal = {
        "seal_version": SEAL_VERSION,
        "snapshot_seal_id": _snapshot_seal_id(
            report_id=_text(payload.get("report_id")),
            replay_hash=replay_hash,
            integrity_hash=integrity_hash,
            divergence_hash=divergence_hash,
        ),
        "report_id": _text(payload.get("report_id")),
        "replay_hash": replay_hash,
        "integrity_hash": integrity_hash,
        "divergence_hash": divergence_hash,
        "repair_chain_ids": repair_chain_ids,
        "source_record_count": source_count,
    }
    return seal


def seal_replay_diff_summary(diff_summary: Any) -> Dict[str, Any]:
    payload = _mapping(diff_summary)
    summary = generate_stable_diff_summary(payload)
    repair_chain_ids = [
        _text(item)
        for item in summary.get("affected_repair_chain_ids", [])
        if _text(item)
    ]
    replay_hash = generate_replay_snapshot_hash(
        {
            "baseline_report_id": summary.get("baseline_report_id"),
            "candidate_report_id": summary.get("candidate_report_id"),
            "replay_drift_count": summary.get("replay_drift_count"),
        }
    )
    integrity_hash = generate_replay_snapshot_hash(payload.get("integrity_delta", {}))
    divergence_hash = generate_replay_snapshot_hash(
        {
            "divergence_count": summary.get("divergence_count"),
            "new_orphan_session_count": summary.get("new_orphan_session_count"),
            "new_chain_break_count": summary.get("new_chain_break_count"),
            "severity_hint": summary.get("severity_hint", {}),
        }
    )
    report_id = _text(summary.get("comparison_id"))
    return {
        "seal_version": SEAL_VERSION,
        "snapshot_seal_id": _snapshot_seal_id(
            report_id=report_id,
            replay_hash=replay_hash,
            integrity_hash=integrity_hash,
            divergence_hash=divergence_hash,
        ),
        "report_id": report_id,
        "replay_hash": replay_hash,
        "integrity_hash": integrity_hash,
        "divergence_hash": divergence_hash,
        "repair_chain_ids": sorted(set(repair_chain_ids)),
        "source_record_count": 0,
    }


def compare_replay_snapshot_seals(
    baseline_seal: Any,
    candidate_seal: Any,
) -> Dict[str, Any]:
    baseline = _mapping(baseline_seal)
    candidate = _mapping(candidate_seal)
    mismatches = detect_replay_snapshot_seal_mismatches(baseline, candidate)
    return {
        "baseline_snapshot_seal_id": _text(baseline.get("snapshot_seal_id")),
        "candidate_snapshot_seal_id": _text(candidate.get("snapshot_seal_id")),
        "seal_mismatch": bool(mismatches),
        "mismatches": mismatches,
        "repair_chain_ids": sorted(
            {
                *[_text(item) for item in baseline.get("repair_chain_ids", []) if _text(item)],
                *[_text(item) for item in candidate.get("repair_chain_ids", []) if _text(item)],
            }
        ),
    }


def detect_replay_snapshot_seal_mismatches(
    baseline_seal: Any,
    candidate_seal: Any,
) -> List[Dict[str, Any]]:
    baseline = _mapping(baseline_seal)
    candidate = _mapping(candidate_seal)
    mismatches: List[Dict[str, Any]] = []
    for field in (
        "report_id",
        "replay_hash",
        "integrity_hash",
        "divergence_hash",
        "repair_chain_ids",
        "source_record_count",
        "seal_version",
    ):
        if baseline.get(field) != candidate.get(field):
            mismatches.append(
                {
                    "field": field,
                    "baseline": copy.deepcopy(baseline.get(field)),
                    "candidate": copy.deepcopy(candidate.get(field)),
                }
            )
    return mismatches


def generate_replay_snapshot_seal_metadata(seal: Any) -> Dict[str, Any]:
    payload = _mapping(seal)
    return {
        "snapshot_seal_id": _text(payload.get("snapshot_seal_id")),
        "report_id": _text(payload.get("report_id")),
        "repair_chain_ids": copy.deepcopy(payload.get("repair_chain_ids", [])),
        "source_record_count": _safe_int(payload.get("source_record_count")),
        "seal_version": _text(payload.get("seal_version")),
        "hashes": {
            "replay_hash": _text(payload.get("replay_hash")),
            "integrity_hash": _text(payload.get("integrity_hash")),
            "divergence_hash": _text(payload.get("divergence_hash")),
        },
    }


def group_replay_snapshot_seals_by_repair_chain_id(
    seals: Iterable[Any],
) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for seal in seals:
        payload = _mapping(seal)
        for repair_chain_id in payload.get("repair_chain_ids", []) or []:
            repair_chain_id = _text(repair_chain_id)
            if not repair_chain_id:
                continue
            group = groups.setdefault(
                repair_chain_id,
                {
                    "repair_chain_id": repair_chain_id,
                    "snapshot_seal_ids": [],
                    "report_ids": [],
                    "seals": [],
                    "source_record_count": 0,
                },
            )
            seal_id = _text(payload.get("snapshot_seal_id"))
            report_id = _text(payload.get("report_id"))
            if seal_id and seal_id not in group["snapshot_seal_ids"]:
                group["snapshot_seal_ids"].append(seal_id)
            if report_id and report_id not in group["report_ids"]:
                group["report_ids"].append(report_id)
            group["seals"].append(generate_replay_snapshot_seal_metadata(payload))
            group["source_record_count"] += _safe_int(payload.get("source_record_count"))
    return [copy.deepcopy(groups[key]) for key in sorted(groups)]


def generate_replay_reconstruction_snapshot_seal(report: Any) -> Dict[str, Any]:
    """Compatibility alias for sealing reconstruction reports."""

    return seal_replay_reconstruction_report(report)


def generate_replay_forensic_snapshot_seal(report: Any) -> Dict[str, Any]:
    snapshot = generate_replay_reconstruction_forensic_snapshot(report)
    lightweight = summarize_replay_reconstruction_report(report)
    replay_hash = generate_replay_snapshot_hash(snapshot)
    integrity_hash = generate_replay_snapshot_hash(snapshot.get("integrity_summary", {}))
    divergence_hash = generate_replay_snapshot_hash(snapshot.get("replay_divergence_hints", []))
    report_id = _text(lightweight.get("report_id"))
    return {
        "seal_version": SEAL_VERSION,
        "snapshot_seal_id": _snapshot_seal_id(
            report_id=report_id,
            replay_hash=replay_hash,
            integrity_hash=integrity_hash,
            divergence_hash=divergence_hash,
        ),
        "report_id": report_id,
        "replay_hash": replay_hash,
        "integrity_hash": integrity_hash,
        "divergence_hash": divergence_hash,
        "repair_chain_ids": copy.deepcopy(lightweight.get("affected_repair_chain_ids", [])),
        "source_record_count": _safe_int(snapshot.get("source_record_count")),
    }


def _repair_chain_ids_for_report(report: Dict[str, Any]) -> List[str]:
    affected = [
        _text(item)
        for item in report.get("affected_repair_chain_ids", [])
        if _text(item)
    ]
    if affected:
        return sorted(set(affected))
    groups = group_timeline_evidence_by_repair_chain_id(report.get("evidence_bundle", {}))
    return sorted(
        {
            _text(group.get("repair_chain_id"))
            for group in groups
            if _text(group.get("repair_chain_id"))
        }
    )


def _snapshot_seal_id(
    *,
    report_id: str,
    replay_hash: str,
    integrity_hash: str,
    divergence_hash: str,
) -> str:
    return "replay-snapshot-seal-" + _stable_hash(
        {
            "report_id": report_id,
            "replay_hash": replay_hash,
            "integrity_hash": integrity_hash,
            "divergence_hash": divergence_hash,
            "seal_version": SEAL_VERSION,
        }
    )[:16]


def _mapping(value: Any) -> Dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


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
