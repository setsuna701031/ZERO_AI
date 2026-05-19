from __future__ import annotations

import copy
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Iterable, List

from core.runtime.engineering_runtime_observability import (
    find_missing_runtime_refs,
    summarize_session_chain,
)


def build_runtime_timeline_summary(
    records: Iterable[Any],
    *,
    replays: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    """Reconstruct read-only timeline views from runtime continuity records."""

    timeline = reconstruct_runtime_timeline(records, replays=replays)
    missing_refs = find_timeline_missing_refs(timeline)
    return {
        "ordered_timeline": timeline,
        "grouped_by_repair_chain_id": group_timeline_by_repair_chain_id(timeline),
        "missing_parent_refs": missing_refs["missing_parent_refs"],
        "missing_previous_runtime_refs": missing_refs["missing_previous_runtime_refs"],
        "chain_breaks": missing_refs["chain_breaks"],
    }


def reconstruct_runtime_timeline(
    records: Iterable[Any],
    *,
    replays: Iterable[Any] | None = None,
) -> List[Dict[str, Any]]:
    source_records = list(records)
    chain = summarize_session_chain(source_records)
    missing_refs = find_missing_runtime_refs(chain)
    session_breaks = _missing_refs_by_session(missing_refs)
    session_entries = [
        _timeline_entry_from_session(item, _status_for_session(item, source_records), session_breaks)
        for item in chain
    ]
    replay_entries = _timeline_entries_from_replays(
        replays or [],
        continuity_by_session={_text(item.get("session_id")): item for item in chain},
        session_breaks=session_breaks,
    )
    ordered = sorted(
        [*session_entries, *replay_entries],
        key=lambda item: (
            _safe_int(item.get("execution_chain_depth")),
            _safe_int(item.get("sequence")),
            _safe_int(item.get("event_index")),
            _text(item.get("session_id")),
            _text(item.get("replay_id")),
            _text(item.get("event_type")),
        ),
    )
    return [copy.deepcopy(item) for item in ordered]


def group_timeline_by_repair_chain_id(timeline: Iterable[Any]) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for entry in timeline:
        payload = _as_mapping(entry)
        repair_chain_id = _text(payload.get("repair_chain_id"))
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
            },
        )
        copied = copy.deepcopy(payload)
        group["entries"].append(copied)
        session_id = _text(payload.get("session_id"))
        replay_id = _text(payload.get("replay_id"))
        if session_id and session_id not in group["session_ids"]:
            group["session_ids"].append(session_id)
        if replay_id and replay_id not in group["replay_ids"]:
            group["replay_ids"].append(replay_id)
        if copied.get("missing_refs", {}).get("has_chain_break"):
            group["chain_break_count"] += 1

    return [copy.deepcopy(groups[key]) for key in sorted(groups)]


def find_timeline_missing_refs(timeline: Iterable[Any]) -> Dict[str, Any]:
    missing_parent_refs: List[Dict[str, Any]] = []
    missing_previous_refs: List[Dict[str, Any]] = []

    for entry in timeline:
        payload = _as_mapping(entry)
        refs = payload.get("missing_refs") if isinstance(payload.get("missing_refs"), dict) else {}
        session_id = _text(payload.get("session_id"))
        if refs.get("missing_parent_ref"):
            missing_parent_refs.append(
                {
                    "session_id": session_id,
                    "parent_session_id": _text(payload.get("parent_session_id")),
                    "event_type": _text(payload.get("event_type")),
                }
            )
        if refs.get("missing_previous_runtime_state_ref"):
            missing_previous_refs.append(
                {
                    "session_id": session_id,
                    "execution_chain_depth": _safe_int(payload.get("execution_chain_depth")),
                    "event_type": _text(payload.get("event_type")),
                }
            )

    return {
        "missing_parent_refs": missing_parent_refs,
        "missing_previous_runtime_refs": missing_previous_refs,
        "chain_breaks": {
            "missing_parent_ref_count": len(missing_parent_refs),
            "missing_previous_runtime_ref_count": len(missing_previous_refs),
            "total_chain_break_count": len(missing_parent_refs) + len(missing_previous_refs),
        },
    }


def summarize_timeline_missing_parent_refs(timeline: Iterable[Any]) -> List[Dict[str, Any]]:
    return find_timeline_missing_refs(timeline)["missing_parent_refs"]


def summarize_timeline_missing_previous_runtime_refs(timeline: Iterable[Any]) -> List[Dict[str, Any]]:
    return find_timeline_missing_refs(timeline)["missing_previous_runtime_refs"]


def _timeline_entry_from_session(
    item: Dict[str, Any],
    status: str,
    session_breaks: Dict[str, Dict[str, bool]],
) -> Dict[str, Any]:
    session_id = _text(item.get("session_id"))
    missing = _missing_flags(session_breaks, session_id)
    return {
        "session_id": session_id,
        "parent_session_id": _text(item.get("parent_session_id")),
        "replay_id": _text(item.get("replay_id")),
        "repair_chain_id": _text(item.get("repair_chain_id")),
        "execution_chain_depth": _safe_int(item.get("execution_chain_depth")),
        "event_type": "session_continuity",
        "status": _text(status) or "observed",
        "missing_refs": missing,
        "previous_runtime_state_ref": _text(item.get("previous_runtime_state_ref")),
        "sequence": _safe_int(item.get("execution_chain_depth")),
        "event_index": 0,
        "source": "engineering_runtime_continuity",
    }


def _timeline_entries_from_replays(
    replays: Iterable[Any],
    *,
    continuity_by_session: Dict[str, Dict[str, Any]],
    session_breaks: Dict[str, Dict[str, bool]],
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for replay in replays:
        payload = _as_mapping(replay)
        replay_id = _text(payload.get("replay_id"))
        replay_records = payload.get("records")
        if not replay_id or not isinstance(replay_records, list):
            continue

        for index, record in enumerate(replay_records, start=1):
            record_payload = _as_mapping(record)
            session_id = _text(record_payload.get("source_session_id"))
            continuity = continuity_by_session.get(session_id, {})
            missing = _missing_flags(session_breaks, session_id)
            entries.append(
                {
                    "session_id": session_id,
                    "parent_session_id": _text(continuity.get("parent_session_id")),
                    "replay_id": replay_id,
                    "repair_chain_id": _text(continuity.get("repair_chain_id")),
                    "execution_chain_depth": _safe_int(continuity.get("execution_chain_depth")),
                    "event_type": "replay_record",
                    "status": _text(record_payload.get("phase")) or "replayed",
                    "missing_refs": missing,
                    "previous_runtime_state_ref": _text(continuity.get("previous_runtime_state_ref")),
                    "sequence": _safe_int(record_payload.get("replay_sequence") or payload.get("sequence")),
                    "event_index": index,
                    "source": "runtime_replay",
                }
            )
    return entries


def _status_for_session(item: Dict[str, Any], records: Iterable[Any]) -> str:
    session_id = _text(item.get("session_id"))
    for record in records:
        payload = _as_mapping(record)
        continuity = _as_mapping(payload.get("engineering_continuity") or payload.get("engineering_runtime_continuity"))
        if _text(continuity.get("session_id") or payload.get("session_id")) != session_id:
            continue
        status = _text(payload.get("status"))
        if status:
            return status
        lifecycle_records = payload.get("lifecycle_records")
        if isinstance(lifecycle_records, list) and lifecycle_records:
            last = _as_mapping(lifecycle_records[-1])
            phase = _text(last.get("phase"))
            if phase:
                return phase
    return ""


def _missing_refs_by_session(missing_refs: Dict[str, Any]) -> Dict[str, Dict[str, bool]]:
    result: Dict[str, Dict[str, bool]] = {}
    for item in missing_refs.get("missing_parent_refs") or []:
        session_id = _text(_as_mapping(item).get("session_id"))
        result.setdefault(session_id, {})["missing_parent_ref"] = True
    for item in missing_refs.get("missing_previous_runtime_state_refs") or []:
        session_id = _text(_as_mapping(item).get("session_id"))
        result.setdefault(session_id, {})["missing_previous_runtime_state_ref"] = True
    return result


def _missing_flags(session_breaks: Dict[str, Dict[str, bool]], session_id: str) -> Dict[str, bool]:
    flags = session_breaks.get(session_id, {})
    missing_parent = bool(flags.get("missing_parent_ref"))
    missing_previous = bool(flags.get("missing_previous_runtime_state_ref"))
    return {
        "missing_parent_ref": missing_parent,
        "missing_previous_runtime_state_ref": missing_previous,
        "has_chain_break": missing_parent or missing_previous,
    }


def _as_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "to_dict"):
        mapped = value.to_dict()
        return mapped if isinstance(mapped, dict) else {}
    return {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0
