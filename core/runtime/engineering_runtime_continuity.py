from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class EngineeringRuntimeSessionContinuity:
    session_id: str
    parent_session_id: str
    replay_id: str
    repair_chain_id: str
    execution_chain_depth: int
    previous_runtime_state_ref: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_engineering_runtime_continuity(
    *,
    session_id: str,
    parent_session_id: str = "",
    replay_id: str = "",
    repair_chain_id: str = "",
    execution_chain_depth: int | str = 0,
    previous_runtime_state_ref: str = "",
) -> EngineeringRuntimeSessionContinuity:
    clean_session_id = _required_text("session_id", session_id)
    depth = _safe_nonnegative_int(execution_chain_depth)
    return EngineeringRuntimeSessionContinuity(
        session_id=clean_session_id,
        parent_session_id=_text(parent_session_id),
        replay_id=_text(replay_id),
        repair_chain_id=_text(repair_chain_id),
        execution_chain_depth=depth,
        previous_runtime_state_ref=_text(previous_runtime_state_ref),
    )


def build_engineering_runtime_continuity_from_task(
    *,
    session_id: str,
    task: Any,
) -> EngineeringRuntimeSessionContinuity:
    payload = task if isinstance(task, dict) else {}
    return build_engineering_runtime_continuity(
        session_id=session_id,
        parent_session_id=_first_text(payload, "parent_session_id", "runtime_parent_session_id"),
        replay_id=_first_text(payload, "replay_id", "runtime_replay_id"),
        repair_chain_id=_first_text(payload, "repair_chain_id", "runtime_repair_chain_id"),
        execution_chain_depth=_first_value(payload, "execution_chain_depth", "runtime_execution_chain_depth", default=0),
        previous_runtime_state_ref=_first_text(payload, "previous_runtime_state_ref", "runtime_state_ref"),
    )


def continuity_from_mapping(value: Any) -> EngineeringRuntimeSessionContinuity | None:
    if not isinstance(value, dict):
        return None
    session_id = _text(value.get("session_id"))
    if not session_id:
        return None
    return build_engineering_runtime_continuity(
        session_id=session_id,
        parent_session_id=_text(value.get("parent_session_id")),
        replay_id=_text(value.get("replay_id")),
        repair_chain_id=_text(value.get("repair_chain_id")),
        execution_chain_depth=value.get("execution_chain_depth", 0),
        previous_runtime_state_ref=_text(value.get("previous_runtime_state_ref")),
    )


def reconstruct_engineering_runtime_chain(records: Iterable[Any]) -> List[Dict[str, Any]]:
    items: List[EngineeringRuntimeSessionContinuity] = []
    for record in records:
        payload = record.get("engineering_continuity") if isinstance(record, dict) else record
        continuity = continuity_from_mapping(payload)
        if continuity is not None:
            items.append(continuity)
    ordered = sorted(items, key=lambda item: (item.execution_chain_depth, item.session_id))
    return [copy.deepcopy(item.to_dict()) for item in ordered]


def _required_text(field_name: str, value: Any) -> str:
    text = _text(value)
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first_text(payload: Dict[str, Any], *keys: str) -> str:
    value = _first_value(payload, *keys, default="")
    return _text(value)


def _first_value(payload: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return default


def _safe_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return 0
