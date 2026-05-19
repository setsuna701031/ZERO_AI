from __future__ import annotations

import copy
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Iterable, List

from core.runtime.engineering_runtime_continuity import (
    EngineeringRuntimeSessionContinuity,
    continuity_from_mapping,
)


def summarize_engineering_runtime_observability(
    records: Iterable[Any],
    *,
    replays: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    """Build a read-only summary of engineering runtime continuity records."""

    chain = summarize_session_chain(records)
    return {
        "session_chain": chain,
        "replay_lineage": summarize_replay_lineage(chain, replays=replays or []),
        "repair_chain_groups": group_by_repair_chain_id(chain),
        "execution_chain_depth": summarize_execution_chain_depth(chain),
        "missing_refs": find_missing_runtime_refs(chain),
    }


def summarize_session_chain(records: Iterable[Any]) -> List[Dict[str, Any]]:
    continuities = _continuities_from_records(records)
    ordered = sorted(continuities, key=lambda item: (item.execution_chain_depth, item.session_id))
    return [
        {
            "session_id": item.session_id,
            "parent_session_id": item.parent_session_id,
            "replay_id": item.replay_id,
            "repair_chain_id": item.repair_chain_id,
            "execution_chain_depth": item.execution_chain_depth,
            "previous_runtime_state_ref": item.previous_runtime_state_ref,
            "root_session_id": _root_session_id(item, continuities),
            "has_parent_ref": bool(item.parent_session_id),
            "has_previous_runtime_state_ref": bool(item.previous_runtime_state_ref),
        }
        for item in ordered
    ]


def summarize_replay_lineage(
    records: Iterable[Any],
    *,
    replays: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    chain = summarize_session_chain(records)
    groups: Dict[str, Dict[str, Any]] = {}
    for item in chain:
        replay_id = _text(item.get("replay_id"))
        if not replay_id:
            continue

        group = groups.setdefault(
            replay_id,
            {
                "replay_id": replay_id,
                "session_ids": [],
                "repair_chain_ids": [],
                "min_execution_chain_depth": None,
                "max_execution_chain_depth": None,
                "total_sessions": 0,
            },
        )
        session_id = _text(item.get("session_id"))
        repair_chain_id = _text(item.get("repair_chain_id"))
        depth = _safe_int(item.get("execution_chain_depth"))
        if session_id and session_id not in group["session_ids"]:
            group["session_ids"].append(session_id)
        if repair_chain_id and repair_chain_id not in group["repair_chain_ids"]:
            group["repair_chain_ids"].append(repair_chain_id)
        group["min_execution_chain_depth"] = depth if group["min_execution_chain_depth"] is None else min(group["min_execution_chain_depth"], depth)
        group["max_execution_chain_depth"] = depth if group["max_execution_chain_depth"] is None else max(group["max_execution_chain_depth"], depth)
        group["total_sessions"] = len(group["session_ids"])

    return {
        "continuity_replays": [
            copy.deepcopy(groups[key])
            for key in sorted(groups)
        ],
        "runtime_replays": _summarize_runtime_replay_sessions(replays or []),
    }


def _summarize_runtime_replay_sessions(replays: Iterable[Any]) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    for replay in replays:
        payload = _as_mapping(replay)
        replay_id = _text(payload.get("replay_id"))
        if not replay_id:
            continue

        records = payload.get("records")
        replay_records = list(records) if isinstance(records, list) else []
        source_session_ids: List[str] = []
        phases: List[str] = []
        for record in replay_records:
            record_payload = _as_mapping(record)
            source_session_id = _text(record_payload.get("source_session_id"))
            phase = _text(record_payload.get("phase"))
            if source_session_id and source_session_id not in source_session_ids:
                source_session_ids.append(source_session_id)
            if phase:
                phases.append(phase)

        summaries.append(
            {
                "replay_id": replay_id,
                "source_session_id": _text(payload.get("source_session_id")),
                "replay_group": _text(payload.get("replay_group")),
                "sequence": _safe_int(payload.get("sequence")),
                "record_count": len(replay_records),
                "source_session_ids": source_session_ids,
                "phases": phases,
                "verified": bool(payload.get("verified", False)),
                "integrity_record_count": len(payload.get("integrity_records") or []),
            }
        )

    return sorted(summaries, key=lambda item: (item["sequence"], item["replay_id"]))


def group_by_repair_chain_id(records: Iterable[Any]) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for item in summarize_session_chain(records):
        repair_chain_id = _text(item.get("repair_chain_id"))
        if not repair_chain_id:
            continue

        group = groups.setdefault(
            repair_chain_id,
            {
                "repair_chain_id": repair_chain_id,
                "session_ids": [],
                "replay_ids": [],
                "min_execution_chain_depth": None,
                "max_execution_chain_depth": None,
                "total_sessions": 0,
            },
        )
        session_id = _text(item.get("session_id"))
        replay_id = _text(item.get("replay_id"))
        depth = _safe_int(item.get("execution_chain_depth"))
        if session_id and session_id not in group["session_ids"]:
            group["session_ids"].append(session_id)
        if replay_id and replay_id not in group["replay_ids"]:
            group["replay_ids"].append(replay_id)
        group["min_execution_chain_depth"] = depth if group["min_execution_chain_depth"] is None else min(group["min_execution_chain_depth"], depth)
        group["max_execution_chain_depth"] = depth if group["max_execution_chain_depth"] is None else max(group["max_execution_chain_depth"], depth)
        group["total_sessions"] = len(group["session_ids"])

    return [
        copy.deepcopy(groups[key])
        for key in sorted(groups)
    ]


def summarize_execution_chain_depth(records: Iterable[Any]) -> Dict[str, Any]:
    chain = summarize_session_chain(records)
    depth_counts: Dict[int, int] = {}
    deepest_sessions: List[str] = []
    max_depth = 0

    for item in chain:
        depth = _safe_int(item.get("execution_chain_depth"))
        depth_counts[depth] = depth_counts.get(depth, 0) + 1
        if depth > max_depth:
            max_depth = depth
            deepest_sessions = []
        if depth == max_depth:
            deepest_sessions.append(_text(item.get("session_id")))

    return {
        "total_sessions": len(chain),
        "max_depth": max_depth,
        "depth_counts": {
            str(depth): depth_counts[depth]
            for depth in sorted(depth_counts)
        },
        "deepest_session_ids": [
            session_id
            for session_id in deepest_sessions
            if session_id
        ],
    }


def find_missing_runtime_refs(records: Iterable[Any]) -> Dict[str, Any]:
    chain = summarize_session_chain(records)
    session_ids = {
        _text(item.get("session_id"))
        for item in chain
        if _text(item.get("session_id"))
    }
    missing_parent_refs: List[Dict[str, str]] = []
    missing_previous_refs: List[Dict[str, Any]] = []

    for item in chain:
        session_id = _text(item.get("session_id"))
        parent_session_id = _text(item.get("parent_session_id"))
        previous_ref = _text(item.get("previous_runtime_state_ref"))
        depth = _safe_int(item.get("execution_chain_depth"))

        if parent_session_id and parent_session_id not in session_ids:
            missing_parent_refs.append(
                {
                    "session_id": session_id,
                    "parent_session_id": parent_session_id,
                }
            )
        if depth > 0 and not previous_ref:
            missing_previous_refs.append(
                {
                    "session_id": session_id,
                    "execution_chain_depth": depth,
                    "previous_runtime_state_ref": "",
                }
            )

    return {
        "missing_parent_ref_count": len(missing_parent_refs),
        "missing_previous_runtime_state_ref_count": len(missing_previous_refs),
        "missing_parent_refs": missing_parent_refs,
        "missing_previous_runtime_state_refs": missing_previous_refs,
    }


def _continuities_from_records(records: Iterable[Any]) -> List[EngineeringRuntimeSessionContinuity]:
    continuities: List[EngineeringRuntimeSessionContinuity] = []
    for record in records:
        payload = _continuity_payload(record)
        continuity = continuity_from_mapping(payload)
        if continuity is not None:
            continuities.append(continuity)
    return continuities


def _continuity_payload(record: Any) -> Any:
    payload = _as_mapping(record)
    if "engineering_continuity" in payload:
        return payload.get("engineering_continuity")
    if "engineering_runtime_continuity" in payload:
        return payload.get("engineering_runtime_continuity")
    if payload:
        return payload
    return record


def _root_session_id(
    continuity: EngineeringRuntimeSessionContinuity,
    continuities: List[EngineeringRuntimeSessionContinuity],
) -> str:
    by_session_id = {item.session_id: item for item in continuities}
    current = continuity
    seen = set()
    while current.parent_session_id and current.parent_session_id in by_session_id:
        if current.session_id in seen:
            break
        seen.add(current.session_id)
        current = by_session_id[current.parent_session_id]
    return current.session_id


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
