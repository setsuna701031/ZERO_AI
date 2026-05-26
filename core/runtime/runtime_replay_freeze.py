from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping

from core.runtime.runtime_surface_registry import classify_runtime_surface
from core.runtime.runtime_transaction_registry import list_transactions


class ReplayMode(str, Enum):
    READ_ONLY = "read_only"
    VERIFY_ONLY = "verify_only"
    EXECUTION_REPLAY = "execution_replay"
    MUTATION_REPLAY = "mutation_replay"


@dataclass(frozen=True)
class RuntimeReplayEvent:
    event_id: str
    sequence: int
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    audit_refs: tuple[str, ...] = ()
    transaction_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["audit_refs"] = list(self.audit_refs)
        payload["transaction_ids"] = list(self.transaction_ids)
        return payload


@dataclass(frozen=True)
class RuntimeReplayRun:
    replay_run_id: str
    mode: ReplayMode
    source_trace_id: str
    source_transaction_ids: tuple[str, ...]
    replay_source: str
    started_at: str
    finished_at: str
    event_count: int
    transaction_count: int
    mutation_attempted: bool
    mutation_allowed: bool
    authority_required: bool
    transaction_required: bool
    normalized_digest: str
    result_state: str
    audit_refs: tuple[str, ...] = ()
    events: tuple[RuntimeReplayEvent, ...] = ()
    failure_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = self.mode.value
        payload["source_transaction_ids"] = list(self.source_transaction_ids)
        payload["audit_refs"] = list(self.audit_refs)
        payload["events"] = [event.to_dict() for event in self.events]
        return payload


def create_replay_run(
    *,
    event_log: Any,
    mode: ReplayMode | str = ReplayMode.READ_ONLY,
    replay_source: str = "",
    source_trace_id: str = "",
    options: Mapping[str, Any] | None = None,
) -> RuntimeReplayRun:
    replay_mode = ReplayMode(str(mode.value if isinstance(mode, ReplayMode) else mode))
    normalized = normalize_replay_input(event_log, mode=replay_mode, options=options)
    events = tuple(_events_from_normalized(normalized))
    source_transaction_ids = tuple(_collect_transaction_ids(normalized))
    audit_refs = tuple(_collect_audit_refs(normalized))
    mutation_attempted = any(_event_is_mutation(event) for event in events)
    mutation_allowed = replay_mode is ReplayMode.MUTATION_REPLAY
    authority_required = replay_mode in {ReplayMode.EXECUTION_REPLAY, ReplayMode.MUTATION_REPLAY}
    transaction_required = replay_mode is ReplayMode.MUTATION_REPLAY or mutation_attempted and mutation_allowed
    digest = _digest(
        {
            "mode": replay_mode.value,
            "input": normalized,
            "options": _normalize_value(options or {}),
        }
    )
    replay_run_id = "replay_run:" + hashlib.sha256(
        repr((digest, replay_mode.value, source_trace_id, replay_source)).encode(
            "utf-8",
            errors="replace",
        )
    ).hexdigest()[:16]
    failure_reason = ""
    result_state = "verified"
    if replay_mode in {ReplayMode.READ_ONLY, ReplayMode.VERIFY_ONLY} and mutation_attempted:
        result_state = "failed"
        failure_reason = "mutation_intent_not_allowed_in_read_only_replay"
    now = _now()
    return RuntimeReplayRun(
        replay_run_id=replay_run_id,
        mode=replay_mode,
        source_trace_id=str(source_trace_id or _first_trace_id(normalized)),
        source_transaction_ids=source_transaction_ids,
        replay_source=str(replay_source or "runtime_replay_freeze"),
        started_at=now,
        finished_at=now,
        event_count=len(events),
        transaction_count=len(source_transaction_ids),
        mutation_attempted=mutation_attempted,
        mutation_allowed=mutation_allowed,
        authority_required=authority_required,
        transaction_required=transaction_required,
        normalized_digest=digest,
        result_state=result_state,
        audit_refs=audit_refs,
        events=events,
        failure_reason=failure_reason,
    )


def normalize_replay_input(
    event_log: Any,
    *,
    mode: ReplayMode | str = ReplayMode.READ_ONLY,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "events": _normalize_events(event_log),
        "mode": str(mode.value if isinstance(mode, ReplayMode) else mode),
        "options": _normalize_value(options or {}),
    }


def normalize_replay_output(replay_run: RuntimeReplayRun | Mapping[str, Any]) -> dict[str, Any]:
    payload = replay_run.to_dict() if isinstance(replay_run, RuntimeReplayRun) else copy.deepcopy(dict(replay_run))
    for key in ("started_at", "finished_at"):
        if key in payload:
            payload[key] = "<normalized>"
    payload["events"] = _normalize_value(payload.get("events", []))
    return payload


def replay_read_only(event_log: Any, *, replay_source: str = "", options: Mapping[str, Any] | None = None) -> dict[str, Any]:
    run = create_replay_run(
        event_log=event_log,
        mode=ReplayMode.READ_ONLY,
        replay_source=replay_source,
        options=options,
    )
    assert_replay_does_not_mutate(run)
    return normalize_replay_output(run)


def replay_verify_only(event_log: Any, *, replay_source: str = "", options: Mapping[str, Any] | None = None) -> dict[str, Any]:
    run = create_replay_run(
        event_log=event_log,
        mode=ReplayMode.VERIFY_ONLY,
        replay_source=replay_source,
        options=options,
    )
    if run.mutation_allowed:
        raise AssertionError("verify-only replay cannot commit mutation")
    return normalize_replay_output(run)


def assert_replay_is_deterministic(first: Any, second: Any) -> bool:
    first_digest = _digest(normalize_replay_output(first) if isinstance(first, RuntimeReplayRun) else first)
    second_digest = _digest(normalize_replay_output(second) if isinstance(second, RuntimeReplayRun) else second)
    if first_digest != second_digest:
        raise AssertionError("replay output is not deterministic")
    return True


def assert_replay_does_not_mutate(replay_run: RuntimeReplayRun | Mapping[str, Any]) -> bool:
    payload = replay_run.to_dict() if isinstance(replay_run, RuntimeReplayRun) else dict(replay_run)
    if payload.get("mutation_allowed") or payload.get("transaction_required"):
        raise AssertionError("read-only replay cannot mutate")
    before = payload.get("transaction_count", 0)
    after = len(list_transactions())
    if after < int(before or 0):
        raise AssertionError("transaction registry changed unexpectedly")
    return True


def attach_replay_lineage(
    payload: Mapping[str, Any],
    *,
    replay_run: RuntimeReplayRun | Mapping[str, Any],
    original_transaction_id: str = "",
    original_trace_id: str = "",
) -> dict[str, Any]:
    run_payload = replay_run.to_dict() if isinstance(replay_run, RuntimeReplayRun) else dict(replay_run)
    return {
        **copy.deepcopy(dict(payload)),
        "replay_run_id": run_payload.get("replay_run_id"),
        "replay_source": run_payload.get("replay_source"),
        "original_transaction_id": str(original_transaction_id or ""),
        "original_trace_id": str(original_trace_id or run_payload.get("source_trace_id") or ""),
    }


def _normalize_events(event_log: Any) -> list[dict[str, Any]]:
    raw_events = event_log
    if isinstance(event_log, Mapping):
        raw_events = event_log.get("events") or event_log.get("records") or []
    if not isinstance(raw_events, list):
        raw_events = [raw_events]
    normalized = []
    for index, event in enumerate(raw_events):
        payload = _normalize_value(event if isinstance(event, Mapping) else {"payload": event})
        for key in ("timestamp", "created_at", "updated_at", "started_at", "finished_at"):
            payload.pop(key, None)
        sequence = _safe_int(payload.get("sequence"), index)
        payload["sequence"] = sequence
        payload.setdefault("event_id", str(payload.get("id") or f"event:{sequence}"))
        normalized.append(payload)
    return sorted(normalized, key=lambda item: (item.get("sequence", 0), str(item.get("event_id") or "")))


def _events_from_normalized(normalized: Mapping[str, Any]) -> list[RuntimeReplayEvent]:
    events = []
    for index, event in enumerate(normalized.get("events") or []):
        if not isinstance(event, Mapping):
            continue
        events.append(
            RuntimeReplayEvent(
                event_id=str(event.get("event_id") or f"event:{index}"),
                sequence=_safe_int(event.get("sequence"), index),
                event_type=str(event.get("event_type") or event.get("type") or "event"),
                payload=copy.deepcopy(dict(event)),
                audit_refs=tuple(_collect_audit_refs(event)),
                transaction_ids=tuple(_collect_transaction_ids(event)),
            )
        )
    return events


def _event_is_mutation(event: RuntimeReplayEvent) -> bool:
    surface = event.payload.get("surface") or event.payload.get("type") or event.event_type
    return classify_runtime_surface(surface).mutation


def _collect_transaction_ids(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"transaction_id", "original_transaction_id"} and str(item or "").strip():
                found.append(str(item))
            else:
                found.extend(_collect_transaction_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_collect_transaction_ids(item))
    return list(dict.fromkeys(found))


def _collect_audit_refs(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "audit_refs":
                if isinstance(item, list):
                    found.extend(str(ref) for ref in item if str(ref or "").strip())
                elif str(item or "").strip():
                    found.append(str(item))
            else:
                found.extend(_collect_audit_refs(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_collect_audit_refs(item))
    return list(dict.fromkeys(found))


def _first_trace_id(value: Any) -> str:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"trace_id", "source_trace_id", "original_trace_id"} and str(item or "").strip():
                return str(item)
            found = _first_trace_id(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _first_trace_id(item)
            if found:
                return found
    return ""


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        normalized = {}
        for key in sorted(value):
            if key in {"timestamp", "created_at", "updated_at", "started_at", "finished_at"}:
                continue
            normalized[str(key)] = _normalize_value(value[key])
        return normalized
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    return value


def _digest(value: Any) -> str:
    payload = json.dumps(_normalize_value(value), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _now() -> str:
    return datetime.now(UTC).isoformat()
