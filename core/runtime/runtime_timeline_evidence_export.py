from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from core.runtime.runtime_timeline_reconstruction import (
    find_timeline_missing_refs,
    reconstruct_runtime_timeline,
)


SCHEMA_VERSION = "runtime_timeline_evidence.v1"


def build_runtime_timeline_evidence_bundle(
    records: Iterable[Any],
    *,
    replays: Iterable[Any] | None = None,
    include_generated_at: bool = False,
) -> Dict[str, Any]:
    """Export reconstructed runtime timeline data as read-only evidence."""

    source_records = list(records)
    timeline = reconstruct_runtime_timeline(source_records, replays=replays)
    evidence = export_runtime_timeline_evidence(
        timeline,
        source_record_count=len(source_records),
    )
    groups = group_timeline_evidence_by_repair_chain_id(evidence)
    broken_chains = detect_broken_timeline_chains(evidence)
    summary_counts = summarize_timeline_evidence_counts(evidence)

    bundle = {
        "schema_version": SCHEMA_VERSION,
        "source_record_count": len(source_records),
        "timeline_entry_count": len(evidence),
        "chain_break_count": summary_counts["chain_break_count"],
        "timeline": evidence,
        "grouped_by_repair_chain_id": groups,
        "broken_timeline_chains": broken_chains,
        "summary_counts": summary_counts,
    }
    if include_generated_at:
        bundle["generated_at"] = datetime.now(timezone.utc).isoformat()
    return bundle


def export_runtime_timeline_evidence(
    timeline: Iterable[Any],
    *,
    source_record_count: int = 0,
) -> List[Dict[str, Any]]:
    exported: List[Dict[str, Any]] = []
    for entry in timeline:
        payload = entry if isinstance(entry, dict) else {}
        missing_refs = copy.deepcopy(payload.get("missing_refs")) if isinstance(payload.get("missing_refs"), dict) else {}
        has_break = bool(missing_refs.get("has_chain_break"))
        exported.append(
            {
                "session_id": _text(payload.get("session_id")),
                "parent_session_id": _text(payload.get("parent_session_id")),
                "replay_id": _text(payload.get("replay_id")),
                "repair_chain_id": _text(payload.get("repair_chain_id")),
                "execution_chain_depth": _safe_int(payload.get("execution_chain_depth")),
                "event_type": _text(payload.get("event_type")),
                "status": _text(payload.get("status")),
                "missing_refs": {
                    "missing_parent_ref": bool(missing_refs.get("missing_parent_ref")),
                    "missing_previous_runtime_state_ref": bool(missing_refs.get("missing_previous_runtime_state_ref")),
                    "has_chain_break": has_break,
                },
                "chain_break_count": 1 if has_break else 0,
                "source_record_count": max(0, int(source_record_count)),
            }
        )
    return exported


def group_timeline_evidence_by_repair_chain_id(evidence: Any) -> List[Dict[str, Any]]:
    entries = _timeline_entries(evidence)
    groups: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        repair_chain_id = _text(entry.get("repair_chain_id"))
        if not repair_chain_id:
            continue
        group = groups.setdefault(
            repair_chain_id,
            {
                "repair_chain_id": repair_chain_id,
                "entries": [],
                "session_ids": [],
                "replay_ids": [],
                "chain_break_count": 0,
                "source_record_count": _safe_int(entry.get("source_record_count")),
            },
        )
        copied = copy.deepcopy(entry)
        group["entries"].append(copied)
        session_id = _text(entry.get("session_id"))
        replay_id = _text(entry.get("replay_id"))
        if session_id and session_id not in group["session_ids"]:
            group["session_ids"].append(session_id)
        if replay_id and replay_id not in group["replay_ids"]:
            group["replay_ids"].append(replay_id)
        group["chain_break_count"] += _safe_int(entry.get("chain_break_count"))

    return [copy.deepcopy(groups[key]) for key in sorted(groups)]


def detect_broken_timeline_chains(evidence: Any) -> Dict[str, Any]:
    entries = _timeline_entries(evidence)
    missing_refs = find_timeline_missing_refs(entries)
    return {
        "chain_break_count": _safe_int(missing_refs.get("chain_breaks", {}).get("total_chain_break_count")),
        "missing_parent_refs": missing_refs["missing_parent_refs"],
        "missing_previous_runtime_refs": missing_refs["missing_previous_runtime_refs"],
    }


def summarize_timeline_evidence_counts(evidence: Any) -> Dict[str, Any]:
    entries = _timeline_entries(evidence)
    broken = detect_broken_timeline_chains(entries)
    repair_chain_ids = {
        _text(entry.get("repair_chain_id"))
        for entry in entries
        if _text(entry.get("repair_chain_id"))
    }
    replay_ids = {
        _text(entry.get("replay_id"))
        for entry in entries
        if _text(entry.get("replay_id"))
    }
    session_ids = {
        _text(entry.get("session_id"))
        for entry in entries
        if _text(entry.get("session_id"))
    }
    source_count = max([_safe_int(entry.get("source_record_count")) for entry in entries] or [0])
    return {
        "timeline_entry_count": len(entries),
        "source_record_count": source_count,
        "session_count": len(session_ids),
        "replay_count": len(replay_ids),
        "repair_chain_count": len(repair_chain_ids),
        "chain_break_count": broken["chain_break_count"],
        "missing_parent_ref_count": len(broken["missing_parent_refs"]),
        "missing_previous_runtime_ref_count": len(broken["missing_previous_runtime_refs"]),
    }


def _timeline_entries(evidence: Any) -> List[Dict[str, Any]]:
    if isinstance(evidence, dict):
        entries = evidence.get("timeline")
    else:
        entries = evidence
    if not isinstance(entries, list):
        return []
    return [copy.deepcopy(entry) for entry in entries if isinstance(entry, dict)]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0
