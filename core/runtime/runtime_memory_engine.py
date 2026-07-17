from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping


class RuntimeMemoryKind(str, Enum):
    FAILURE_PATTERN = "failure_pattern"
    REPAIR_HISTORY = "repair_history"
    REPLAY_WINDOW = "replay_window"
    TRANSACTION_HISTORY = "transaction_history"
    STABILIZATION_HISTORY = "stabilization_history"
    INVARIANT_VIOLATION = "invariant_violation"
    RECOVERY_TERMINAL = "recovery_terminal"
    EXECUTION_SUMMARY = "execution_summary"
    EVIDENCE_SUMMARY = "evidence_summary"


@dataclass(frozen=True)
class RuntimeMemoryRecord:
    memory_id: str
    kind: RuntimeMemoryKind
    task_id: str = ""
    trace_id: str = ""
    step_id: str = ""
    transaction_id: str = ""
    replay_run_id: str = ""
    recovery_attempt_id: str = ""
    repair_loop_id: str = ""
    evidence_refs: tuple[str, ...] = ()
    invariant_refs: tuple[str, ...] = ()
    summary: str = ""
    semantic_tags: tuple[str, ...] = ()
    failure_signature: str = ""
    repair_strategy: str = ""
    stabilization_result: str = ""
    terminal_state: str = ""
    created_at: str = ""
    updated_at: str = ""
    normalized_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        for key in ("evidence_refs", "invariant_refs", "semantic_tags"):
            payload[key] = list(getattr(self, key))
        return payload


_MEMORY_RECORD_CLS = RuntimeMemoryRecord


@dataclass(frozen=True)
class RuntimeMemoryWindow:
    window_id: str
    memory_ids: tuple[str, ...]
    trace_id: str = ""
    replay_run_id: str = ""
    start_sequence: int = 0
    end_sequence: int = 0
    compacted: bool = False
    lineage_refs: tuple[str, ...] = ()
    normalized_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["memory_ids"] = list(self.memory_ids)
        payload["lineage_refs"] = list(self.lineage_refs)
        return payload


@dataclass(frozen=True)
class RuntimeMemoryQuery:
    trace_id: str = ""
    transaction_id: str = ""
    replay_run_id: str = ""
    recovery_attempt_id: str = ""
    repair_loop_id: str = ""
    failure_signature: str = ""
    repair_strategy: str = ""
    terminal_state: str = ""
    semantic_tag: str = ""
    kind: RuntimeMemoryKind | str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if isinstance(self.kind, RuntimeMemoryKind):
            payload["kind"] = self.kind.value
        return payload


@dataclass(frozen=True)
class RuntimeMemorySnapshot:
    snapshot_id: str
    memory_ids: tuple[str, ...]
    records: tuple[RuntimeMemoryRecord, ...] = ()
    windows: tuple[RuntimeMemoryWindow, ...] = ()
    compacted: bool = False
    lineage_refs: tuple[str, ...] = ()
    created_at: str = ""
    normalized_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["memory_ids"] = list(self.memory_ids)
        payload["records"] = [record.to_dict() for record in self.records]
        payload["windows"] = [window.to_dict() for window in self.windows]
        payload["lineage_refs"] = list(self.lineage_refs)
        return payload


_MEMORY: dict[str, RuntimeMemoryRecord] = {}
_WINDOWS: dict[str, RuntimeMemoryWindow] = {}


def create_memory_record(
    *,
    kind: RuntimeMemoryKind | str,
    task_id: str = "",
    trace_id: str = "",
    step_id: str = "",
    transaction_id: str = "",
    replay_run_id: str = "",
    recovery_attempt_id: str = "",
    repair_loop_id: str = "",
    evidence_refs: Any = None,
    invariant_refs: Any = None,
    summary: str = "",
    semantic_tags: Any = None,
    failure_signature: str = "",
    repair_strategy: str = "",
    stabilization_result: str = "",
    terminal_state: str = "",
) -> RuntimeMemoryRecord:
    memory_kind = RuntimeMemoryKind(str(kind.value if isinstance(kind, RuntimeMemoryKind) else kind))
    base = {
        "kind": memory_kind.value,
        "task_id": str(task_id or ""),
        "trace_id": str(trace_id or ""),
        "step_id": str(step_id or ""),
        "transaction_id": str(transaction_id or ""),
        "replay_run_id": str(replay_run_id or ""),
        "recovery_attempt_id": str(recovery_attempt_id or ""),
        "repair_loop_id": str(repair_loop_id or ""),
        "evidence_refs": list(_text_tuple(evidence_refs)),
        "invariant_refs": list(_text_tuple(invariant_refs)),
        "summary": str(summary or ""),
        "semantic_tags": sorted(set(_text_tuple(semantic_tags))),
        "failure_signature": str(failure_signature or ""),
        "repair_strategy": str(repair_strategy or ""),
        "stabilization_result": str(stabilization_result or ""),
        "terminal_state": str(terminal_state or ""),
    }
    digest = _digest(base)
    now = _now()
    return _MEMORY_RECORD_CLS(
        memory_id="runtime_memory:" + digest[:16],
        kind=memory_kind,
        task_id=base["task_id"],
        trace_id=base["trace_id"],
        step_id=base["step_id"],
        transaction_id=base["transaction_id"],
        replay_run_id=base["replay_run_id"],
        recovery_attempt_id=base["recovery_attempt_id"],
        repair_loop_id=base["repair_loop_id"],
        evidence_refs=tuple(base["evidence_refs"]),
        invariant_refs=tuple(base["invariant_refs"]),
        summary=base["summary"],
        semantic_tags=tuple(base["semantic_tags"]),
        failure_signature=base["failure_signature"],
        repair_strategy=base["repair_strategy"],
        stabilization_result=base["stabilization_result"],
        terminal_state=base["terminal_state"],
        created_at=now,
        updated_at=now,
        normalized_digest=digest,
    )


def append_runtime_memory(record: RuntimeMemoryRecord | Mapping[str, Any]) -> RuntimeMemoryRecord:
    item = _record_from_any(record)
    assert_memory_non_authoritative(item)
    _MEMORY[item.memory_id] = item
    return item


def build_memory_window(
    records: Any = None,
    *,
    trace_id: str = "",
    replay_run_id: str = "",
    start_sequence: int = 0,
    end_sequence: int = 0,
) -> RuntimeMemoryWindow:
    memory_records = _records_from_any(records if records is not None else _MEMORY.values())
    if trace_id:
        memory_records = [record for record in memory_records if record.trace_id == trace_id]
    if replay_run_id:
        memory_records = [record for record in memory_records if record.replay_run_id == replay_run_id]
    memory_records = sorted(memory_records, key=lambda item: (item.trace_id, item.replay_run_id, item.memory_id))
    memory_ids = tuple(record.memory_id for record in memory_records)
    lineage_refs = _lineage_refs(memory_records)
    digest_payload = {
        "memory_ids": list(memory_ids),
        "trace_id": trace_id,
        "replay_run_id": replay_run_id,
        "start_sequence": int(start_sequence or 0),
        "end_sequence": int(end_sequence or len(memory_ids)),
        "lineage_refs": list(lineage_refs),
    }
    digest = _digest(digest_payload)
    window = RuntimeMemoryWindow(
        window_id="runtime_memory_window:" + digest[:16],
        memory_ids=memory_ids,
        trace_id=str(trace_id or ""),
        replay_run_id=str(replay_run_id or ""),
        start_sequence=int(start_sequence or 0),
        end_sequence=int(end_sequence or len(memory_ids)),
        lineage_refs=lineage_refs,
        normalized_digest=digest,
    )
    _WINDOWS[window.window_id] = window
    return window


def compact_memory_window(window: RuntimeMemoryWindow | Mapping[str, Any], *, max_records: int = 50) -> RuntimeMemoryWindow:
    payload = window.to_dict() if isinstance(window, RuntimeMemoryWindow) else dict(window)
    memory_ids = tuple(str(item) for item in payload.get("memory_ids", []) if str(item or "").strip())
    bounded = memory_ids[-max(1, int(max_records or 1)) :]
    lineage_refs = tuple(dict.fromkeys([*payload.get("lineage_refs", []), *memory_ids]))
    digest_payload = {
        "memory_ids": list(bounded),
        "trace_id": payload.get("trace_id", ""),
        "replay_run_id": payload.get("replay_run_id", ""),
        "lineage_refs": list(lineage_refs),
        "compacted": True,
    }
    digest = _digest(digest_payload)
    compacted = RuntimeMemoryWindow(
        window_id="runtime_memory_window:" + digest[:16],
        memory_ids=bounded,
        trace_id=str(payload.get("trace_id") or ""),
        replay_run_id=str(payload.get("replay_run_id") or ""),
        start_sequence=int(payload.get("start_sequence") or 0),
        end_sequence=int(payload.get("end_sequence") or len(bounded)),
        compacted=True,
        lineage_refs=lineage_refs,
        normalized_digest=digest,
    )
    _WINDOWS[compacted.window_id] = compacted
    return compacted


def query_runtime_memory(query: RuntimeMemoryQuery | Mapping[str, Any] | None = None, **criteria: Any) -> tuple[RuntimeMemoryRecord, ...]:
    payload = query.to_dict() if isinstance(query, RuntimeMemoryQuery) else dict(query or {})
    payload.update({key: value for key, value in criteria.items() if value is not None})
    values = list(_MEMORY.values())
    kind = payload.get("kind")
    if isinstance(kind, RuntimeMemoryKind):
        kind = kind.value
    for key in ("trace_id", "transaction_id", "replay_run_id", "recovery_attempt_id", "repair_loop_id", "failure_signature", "repair_strategy", "terminal_state"):
        if payload.get(key):
            values = [record for record in values if getattr(record, key) == str(payload[key])]
    if payload.get("semantic_tag"):
        values = [record for record in values if str(payload["semantic_tag"]) in record.semantic_tags]
    if kind:
        values = [record for record in values if record.kind.value == str(kind)]
    return tuple(sorted(values, key=lambda item: item.memory_id))


def query_failure_patterns(**criteria: Any) -> tuple[RuntimeMemoryRecord, ...]:
    return query_runtime_memory(kind=RuntimeMemoryKind.FAILURE_PATTERN, **criteria)


def query_repair_history(**criteria: Any) -> tuple[RuntimeMemoryRecord, ...]:
    return query_runtime_memory(kind=RuntimeMemoryKind.REPAIR_HISTORY, **criteria)


def query_stabilization_history(**criteria: Any) -> tuple[RuntimeMemoryRecord, ...]:
    return query_runtime_memory(kind=RuntimeMemoryKind.STABILIZATION_HISTORY, **criteria)


def retrieve_experience_memory(**criteria: Any) -> RuntimeMemorySnapshot:
    records = query_runtime_memory(**criteria)
    return _snapshot(records)


def retrieve_replay_window(*, trace_id: str = "", replay_run_id: str = "") -> RuntimeMemoryWindow:
    return build_memory_window(query_runtime_memory(trace_id=trace_id, replay_run_id=replay_run_id), trace_id=trace_id, replay_run_id=replay_run_id)


def retrieve_repair_memory(**criteria: Any) -> RuntimeMemorySnapshot:
    records = query_repair_history(**criteria)
    if criteria.get("failure_signature"):
        records = tuple(dict.fromkeys([*records, *query_failure_patterns(failure_signature=criteria["failure_signature"])]))
    return _snapshot(records)


def normalize_memory_snapshot(snapshot: RuntimeMemorySnapshot | Mapping[str, Any]) -> dict[str, Any]:
    payload = snapshot.to_dict() if isinstance(snapshot, RuntimeMemorySnapshot) else copy.deepcopy(dict(snapshot))
    return _normalize_value(payload)


def assert_memory_snapshot_stable(first: RuntimeMemorySnapshot | Mapping[str, Any], second: RuntimeMemorySnapshot | Mapping[str, Any] | None = None) -> bool:
    first_payload = normalize_memory_snapshot(first)
    second_payload = normalize_memory_snapshot(second if second is not None else first)
    if _digest(first_payload) != _digest(second_payload):
        raise AssertionError("runtime memory snapshot is not deterministic")
    return True


def assert_memory_non_authoritative(value: RuntimeMemoryRecord | Mapping[str, Any]) -> bool:
    payload = value.to_dict() if isinstance(value, RuntimeMemoryRecord) else dict(value)
    forbidden = {"execution_authority", "authority_metadata", "execution_authority_metadata"}
    if forbidden & set(payload):
        raise AssertionError("runtime memory cannot grant authority")
    if payload.get("authority_granted") or payload.get("approval_state") in {"approved", "allowed"}:
        raise AssertionError("runtime memory cannot be authority")
    if payload.get("creates_transaction") or payload.get("transaction_created"):
        raise AssertionError("runtime memory cannot create transaction")
    return True


def assert_memory_preserves_lineage(value: RuntimeMemorySnapshot | RuntimeMemoryRecord | RuntimeMemoryWindow | Mapping[str, Any]) -> bool:
    payload = value.to_dict() if hasattr(value, "to_dict") else dict(value)
    if payload.get("records"):
        for record in payload["records"]:
            assert_memory_preserves_lineage(record)
        return True
    if payload.get("memory_ids") is not None:
        if payload.get("compacted") and not payload.get("lineage_refs"):
            raise AssertionError("compacted memory window must preserve lineage")
        return True
    lineage_keys = ("transaction_id", "replay_run_id", "recovery_attempt_id", "repair_loop_id", "evidence_refs", "invariant_refs")
    if not any(payload.get(key) for key in lineage_keys):
        raise AssertionError("runtime memory record has no lineage refs")
    return True


def memory_refs_for_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    records: list[RuntimeMemoryRecord] = []
    if isinstance(payload.get("autonomous_repair_loop"), Mapping):
        records.extend(memory_records_for_repair_loop(payload["autonomous_repair_loop"]))
    if isinstance(payload.get("runtime_recovery"), Mapping):
        records.append(memory_record_for_recovery(payload["runtime_recovery"]))
    if isinstance(payload.get("runtime_replay"), Mapping):
        records.append(memory_record_for_replay(payload["runtime_replay"]))
    if isinstance(payload.get("canonical_evidence"), Mapping):
        evidence_refs = payload["canonical_evidence"].get("evidence_refs") or []
        if evidence_refs:
            records.append(
                create_memory_record(
                    kind=RuntimeMemoryKind.EVIDENCE_SUMMARY,
                    evidence_refs=evidence_refs,
                    summary="canonical evidence summary",
                    semantic_tags=["evidence", "lineage"],
                )
            )
    appended = [append_runtime_memory(record) for record in records if record is not None]
    return {"memory_refs": [record.memory_id for record in appended]}


def memory_records_for_repair_loop(loop: Mapping[str, Any] | Any) -> tuple[RuntimeMemoryRecord, ...]:
    data = loop.to_dict() if hasattr(loop, "to_dict") else dict(loop)
    records = [
        create_memory_record(
            kind=RuntimeMemoryKind.REPAIR_HISTORY,
            task_id=str(data.get("task_id") or ""),
            trace_id=str(data.get("trace_id") or ""),
            step_id=str(data.get("step_id") or ""),
            transaction_id=",".join(str(item) for item in data.get("transaction_refs", []) if str(item or "").strip()),
            replay_run_id=str(data.get("source_replay_run_id") or ""),
            recovery_attempt_id=str(data.get("source_recovery_attempt_id") or ""),
            repair_loop_id=str(data.get("loop_id") or ""),
            evidence_refs=data.get("evidence_refs"),
            invariant_refs=data.get("invariant_refs"),
            summary="autonomous repair loop completed",
            semantic_tags=["repair", "experience", str(data.get("final_state") or "")],
            failure_signature=str(data.get("source_failure_id") or ""),
            repair_strategy=str((data.get("repair_strategy") or {}).get("strategy_id") if isinstance(data.get("repair_strategy"), Mapping) else ""),
            terminal_state=str(data.get("final_state") or ""),
        )
    ]
    if str(data.get("final_state") or "") in {"failed_terminal", "rolled_back", "requires_human_review", "blocked"} or data.get("source_failure_id"):
        records.append(
            create_memory_record(
                kind=RuntimeMemoryKind.FAILURE_PATTERN,
                task_id=str(data.get("task_id") or ""),
                trace_id=str(data.get("trace_id") or ""),
                step_id=str(data.get("step_id") or ""),
                transaction_id=",".join(str(item) for item in data.get("transaction_refs", []) if str(item or "").strip()),
                replay_run_id=str(data.get("source_replay_run_id") or ""),
                recovery_attempt_id=str(data.get("source_recovery_attempt_id") or ""),
                repair_loop_id=str(data.get("loop_id") or ""),
                evidence_refs=data.get("evidence_refs"),
                invariant_refs=data.get("invariant_refs"),
                summary="failure pattern from repair loop",
                semantic_tags=["failure", "repair", str(data.get("final_state") or "")],
                failure_signature=str(data.get("source_failure_id") or ""),
                repair_strategy=str((data.get("repair_strategy") or {}).get("strategy_id") if isinstance(data.get("repair_strategy"), Mapping) else ""),
                terminal_state=str(data.get("final_state") or ""),
            )
        )
    if data.get("stabilized") or str(data.get("final_state") or "") == "stabilized":
        records.append(
            create_memory_record(
                kind=RuntimeMemoryKind.STABILIZATION_HISTORY,
                task_id=str(data.get("task_id") or ""),
                trace_id=str(data.get("trace_id") or ""),
                step_id=str(data.get("step_id") or ""),
                transaction_id=",".join(str(item) for item in data.get("transaction_refs", []) if str(item or "").strip()),
                replay_run_id=str(data.get("source_replay_run_id") or ""),
                recovery_attempt_id=str(data.get("source_recovery_attempt_id") or ""),
                repair_loop_id=str(data.get("loop_id") or ""),
                evidence_refs=data.get("evidence_refs"),
                invariant_refs=data.get("invariant_refs"),
                summary="repair loop stabilized",
                semantic_tags=["stabilization", "repair"],
                failure_signature=str(data.get("source_failure_id") or ""),
                repair_strategy=str((data.get("repair_strategy") or {}).get("strategy_id") if isinstance(data.get("repair_strategy"), Mapping) else ""),
                stabilization_result="stabilized",
                terminal_state=str(data.get("final_state") or ""),
            )
        )
    return tuple(records)


def memory_record_for_recovery(recovery: Mapping[str, Any] | Any) -> RuntimeMemoryRecord:
    data = recovery.to_dict() if hasattr(recovery, "to_dict") else dict(recovery)
    return create_memory_record(
        kind=RuntimeMemoryKind.RECOVERY_TERMINAL,
        trace_id=str(data.get("original_trace_id") or ""),
        transaction_id=str(data.get("original_transaction_id") or data.get("recovery_transaction_id") or ""),
        replay_run_id=str(data.get("replay_run_id") or ""),
        recovery_attempt_id=str(data.get("recovery_attempt_id") or ""),
        evidence_refs=[data.get("evidence_id")] if data.get("evidence_id") else [],
        summary="recovery terminal state",
        semantic_tags=["recovery", "terminal", str(data.get("state") or "")],
        failure_signature=str((data.get("failure_result") or {}).get("reason") if isinstance(data.get("failure_result"), Mapping) else ""),
        terminal_state=str(data.get("state") or ""),
    )


def memory_record_for_replay(replay: Mapping[str, Any] | Any) -> RuntimeMemoryRecord:
    data = replay.to_dict() if hasattr(replay, "to_dict") else dict(replay)
    return create_memory_record(
        kind=RuntimeMemoryKind.REPLAY_WINDOW,
        trace_id=str(data.get("source_trace_id") or ""),
        transaction_id=",".join(str(item) for item in data.get("source_transaction_ids", []) if str(item or "").strip()),
        replay_run_id=str(data.get("replay_run_id") or ""),
        evidence_refs=[data.get("evidence_id")] if data.get("evidence_id") else [],
        summary="replay window memory",
        semantic_tags=["replay", "window", str(data.get("mode") or "")],
        failure_signature=str(data.get("failure_reason") or ""),
        terminal_state=str(data.get("result_state") or ""),
    )


def memory_record_for_invariant_violation(violation: Mapping[str, Any] | Any) -> RuntimeMemoryRecord:
    data = violation.to_dict() if hasattr(violation, "to_dict") else dict(violation)
    invariant = str(data.get("invariant") or "")
    context = data.get("context") if isinstance(data.get("context"), Mapping) else {}
    return create_memory_record(
        kind=RuntimeMemoryKind.INVARIANT_VIOLATION,
        trace_id=str(context.get("trace_id") or ""),
        transaction_id=str(context.get("transaction_id") or ""),
        repair_loop_id=str(context.get("loop_id") or ""),
        invariant_refs=[invariant],
        summary=str(data.get("reason") or "runtime invariant violation"),
        semantic_tags=["invariant", invariant.split(".", 1)[0] if invariant else "runtime"],
        failure_signature=str(data.get("reason") or ""),
        terminal_state="blocked" if data.get("blocked", True) else "",
    )


def memory_record_for_burnin(result: Mapping[str, Any] | Any) -> RuntimeMemoryRecord:
    data = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    return create_memory_record(
        kind=RuntimeMemoryKind.STABILIZATION_HISTORY,
        summary="runtime burn-in stabilization",
        semantic_tags=["burnin", "stabilization"],
        stabilization_result="stable" if data.get("ok") else "unstable",
        terminal_state="stabilized" if data.get("ok") else "failed_terminal",
    )


def _snapshot(records: Any, *, windows: Any = None, compacted: bool = False) -> RuntimeMemorySnapshot:
    memory_records = tuple(sorted(_records_from_any(records), key=lambda item: item.memory_id))
    memory_ids = tuple(record.memory_id for record in memory_records)
    memory_windows = tuple(_window_from_any(window) for window in _iter_any(windows))
    lineage_refs = tuple(dict.fromkeys([*_lineage_refs(memory_records), *(ref for window in memory_windows for ref in window.lineage_refs)]))
    digest_payload = {
        "memory_ids": list(memory_ids),
        "records": [record.to_dict() for record in memory_records],
        "windows": [window.to_dict() for window in memory_windows],
        "compacted": compacted,
        "lineage_refs": list(lineage_refs),
    }
    digest = _digest(digest_payload)
    return RuntimeMemorySnapshot(
        snapshot_id="runtime_memory_snapshot:" + digest[:16],
        memory_ids=memory_ids,
        records=memory_records,
        windows=memory_windows,
        compacted=compacted,
        lineage_refs=lineage_refs,
        created_at=_now(),
        normalized_digest=digest,
    )


def _record_from_any(value: RuntimeMemoryRecord | Mapping[str, Any]) -> RuntimeMemoryRecord:
    if isinstance(value, RuntimeMemoryRecord):
        return value
    return create_memory_record(**dict(value))


def _records_from_any(value: Any) -> list[RuntimeMemoryRecord]:
    return [_record_from_any(item) for item in _iter_any(value)]


def _window_from_any(value: RuntimeMemoryWindow | Mapping[str, Any]) -> RuntimeMemoryWindow:
    if isinstance(value, RuntimeMemoryWindow):
        return value
    payload = dict(value)
    digest = payload.get("normalized_digest") or _digest(payload)
    return RuntimeMemoryWindow(
        window_id=str(payload.get("window_id") or "runtime_memory_window:" + digest[:16]),
        memory_ids=tuple(payload.get("memory_ids") or ()),
        trace_id=str(payload.get("trace_id") or ""),
        replay_run_id=str(payload.get("replay_run_id") or ""),
        start_sequence=int(payload.get("start_sequence") or 0),
        end_sequence=int(payload.get("end_sequence") or 0),
        compacted=bool(payload.get("compacted")),
        lineage_refs=tuple(payload.get("lineage_refs") or ()),
        normalized_digest=str(digest),
    )


def _iter_any(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (RuntimeMemoryRecord, RuntimeMemoryWindow, Mapping, str)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _lineage_refs(records: list[RuntimeMemoryRecord] | tuple[RuntimeMemoryRecord, ...]) -> tuple[str, ...]:
    refs: list[str] = []
    for record in records:
        refs.extend(
            [
                record.transaction_id,
                record.replay_run_id,
                record.recovery_attempt_id,
                record.repair_loop_id,
                *record.evidence_refs,
                *record.invariant_refs,
            ]
        )
    return tuple(dict.fromkeys(str(ref) for ref in refs if str(ref or "").strip()))


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Mapping):
        values = list(value.values())
    else:
        try:
            values = list(value)
        except TypeError:
            values = [value]
    return tuple(str(item) for item in values if str(item or "").strip())


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(value[key]) for key in sorted(value) if key not in {"created_at", "updated_at", "timestamp", "started_at", "finished_at"}}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return copy.deepcopy(value)


def _digest(value: Any) -> str:
    payload = json.dumps(_normalize_value(value), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()
