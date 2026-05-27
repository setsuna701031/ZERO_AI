from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping

from core.runtime.runtime_memory_engine import (
    RuntimeMemoryRecord as _RuntimeMemoryRecord,
    assert_memory_non_authoritative,
    assert_memory_preserves_lineage,
)

RuntimeMemoryRecord = _RuntimeMemoryRecord


@dataclass(frozen=True)
class RuntimeMemoryIndex:
    index_id: str
    memory_ids: tuple[str, ...]
    by_trace: dict[str, tuple[str, ...]] = field(default_factory=dict)
    by_failure_signature: dict[str, tuple[str, ...]] = field(default_factory=dict)
    by_repair_strategy: dict[str, tuple[str, ...]] = field(default_factory=dict)
    by_transaction: dict[str, tuple[str, ...]] = field(default_factory=dict)
    by_terminal_state: dict[str, tuple[str, ...]] = field(default_factory=dict)
    by_semantic_tag: dict[str, tuple[str, ...]] = field(default_factory=dict)
    compacted: bool = False
    lineage_refs: tuple[str, ...] = ()
    normalized_digest: str = ""
    records: tuple[RuntimeMemoryRecord, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["memory_ids"] = list(self.memory_ids)
        payload["lineage_refs"] = list(self.lineage_refs)
        payload["records"] = [record.to_dict() for record in self.records]
        for key in (
            "by_trace",
            "by_failure_signature",
            "by_repair_strategy",
            "by_transaction",
            "by_terminal_state",
            "by_semantic_tag",
        ):
            payload[key] = {item_key: list(values) for item_key, values in getattr(self, key).items()}
        return payload


def index_runtime_memory(records: Any) -> RuntimeMemoryIndex:
    memory_records = tuple(sorted(_records_from_any(records), key=lambda item: item.memory_id))
    for record in memory_records:
        assert_memory_non_authoritative(record)
    memory_ids = tuple(record.memory_id for record in memory_records)
    by_trace = _build_index(memory_records, "trace_id")
    by_failure_signature = _build_index(memory_records, "failure_signature")
    by_repair_strategy = _build_index(memory_records, "repair_strategy")
    by_transaction = _build_index(memory_records, "transaction_id")
    by_terminal_state = _build_index(memory_records, "terminal_state")
    by_semantic_tag: dict[str, tuple[str, ...]] = {}
    for record in memory_records:
        for tag in record.semantic_tags:
            by_semantic_tag.setdefault(tag, tuple())
            by_semantic_tag[tag] = tuple(dict.fromkeys([*by_semantic_tag[tag], record.memory_id]))
    lineage_refs = _lineage_refs(memory_records)
    digest_payload = {
        "memory_ids": list(memory_ids),
        "by_trace": by_trace,
        "by_failure_signature": by_failure_signature,
        "by_repair_strategy": by_repair_strategy,
        "by_transaction": by_transaction,
        "by_terminal_state": by_terminal_state,
        "by_semantic_tag": by_semantic_tag,
        "lineage_refs": list(lineage_refs),
        "compacted": False,
    }
    digest = _digest(digest_payload)
    return RuntimeMemoryIndex(
        index_id="runtime_memory_index:" + digest[:16],
        memory_ids=memory_ids,
        by_trace=by_trace,
        by_failure_signature=by_failure_signature,
        by_repair_strategy=by_repair_strategy,
        by_transaction=by_transaction,
        by_terminal_state=by_terminal_state,
        by_semantic_tag=by_semantic_tag,
        lineage_refs=lineage_refs,
        normalized_digest=digest,
        records=memory_records,
    )


def query_memory_by_trace(index: RuntimeMemoryIndex, trace_id: str) -> tuple[RuntimeMemoryRecord, ...]:
    return _records_for_ids(index, index.by_trace.get(str(trace_id), ()))


def query_memory_by_failure_signature(index: RuntimeMemoryIndex, failure_signature: str) -> tuple[RuntimeMemoryRecord, ...]:
    return _records_for_ids(index, index.by_failure_signature.get(str(failure_signature), ()))


def query_memory_by_repair_strategy(index: RuntimeMemoryIndex, repair_strategy: str) -> tuple[RuntimeMemoryRecord, ...]:
    return _records_for_ids(index, index.by_repair_strategy.get(str(repair_strategy), ()))


def query_memory_by_transaction(index: RuntimeMemoryIndex, transaction_id: str) -> tuple[RuntimeMemoryRecord, ...]:
    return _records_for_ids(index, index.by_transaction.get(str(transaction_id), ()))


def query_memory_by_terminal_state(index: RuntimeMemoryIndex, terminal_state: str) -> tuple[RuntimeMemoryRecord, ...]:
    return _records_for_ids(index, index.by_terminal_state.get(str(terminal_state), ()))


def query_memory_by_semantic_tag(index: RuntimeMemoryIndex, semantic_tag: str) -> tuple[RuntimeMemoryRecord, ...]:
    return _records_for_ids(index, index.by_semantic_tag.get(str(semantic_tag), ()))


def compact_memory_index(index: RuntimeMemoryIndex, *, max_records: int = 50) -> RuntimeMemoryIndex:
    records = index.records[-max(1, int(max_records or 1)) :]
    compacted = index_runtime_memory(records)
    lineage_refs = tuple(dict.fromkeys([*index.lineage_refs, *index.memory_ids, *compacted.lineage_refs]))
    digest_payload = {
        "memory_ids": list(compacted.memory_ids),
        "by_trace": compacted.by_trace,
        "by_failure_signature": compacted.by_failure_signature,
        "by_repair_strategy": compacted.by_repair_strategy,
        "by_transaction": compacted.by_transaction,
        "by_terminal_state": compacted.by_terminal_state,
        "by_semantic_tag": compacted.by_semantic_tag,
        "lineage_refs": list(lineage_refs),
        "compacted": True,
    }
    digest = _digest(digest_payload)
    return RuntimeMemoryIndex(
        index_id="runtime_memory_index:" + digest[:16],
        memory_ids=compacted.memory_ids,
        by_trace=compacted.by_trace,
        by_failure_signature=compacted.by_failure_signature,
        by_repair_strategy=compacted.by_repair_strategy,
        by_transaction=compacted.by_transaction,
        by_terminal_state=compacted.by_terminal_state,
        by_semantic_tag=compacted.by_semantic_tag,
        compacted=True,
        lineage_refs=lineage_refs,
        normalized_digest=digest,
        records=compacted.records,
    )


def assert_memory_index_integrity(index: RuntimeMemoryIndex | Mapping[str, Any]) -> bool:
    payload = index.to_dict() if isinstance(index, RuntimeMemoryIndex) else dict(index)
    memory_ids = set(payload.get("memory_ids") or [])
    for key in ("by_trace", "by_failure_signature", "by_repair_strategy", "by_transaction", "by_terminal_state", "by_semantic_tag"):
        values = payload.get(key) or {}
        for refs in values.values():
            if not set(refs).issubset(memory_ids):
                raise AssertionError("runtime memory index references unknown memory id")
    if payload.get("compacted") and not payload.get("lineage_refs"):
        raise AssertionError("compacted memory index must preserve lineage")
    for record in payload.get("records") or []:
        assert_memory_non_authoritative(record)
        assert_memory_preserves_lineage(record)
    return True


def _records_for_ids(index: RuntimeMemoryIndex, memory_ids: Any) -> tuple[RuntimeMemoryRecord, ...]:
    ids = set(str(item) for item in memory_ids)
    return tuple(record for record in index.records if record.memory_id in ids)


def _records_from_any(value: Any) -> list[RuntimeMemoryRecord]:
    if value is None:
        return []
    if isinstance(value, RuntimeMemoryRecord):
        return [value]
    if isinstance(value, Mapping):
        return [_RuntimeMemoryRecord(**_record_kwargs(value))]
    try:
        values = list(value)
    except TypeError:
        values = [value]
    return [item if isinstance(item, RuntimeMemoryRecord) else _RuntimeMemoryRecord(**_record_kwargs(item)) for item in values]


def _record_kwargs(value: Any) -> dict[str, Any]:
    payload = value.to_dict() if hasattr(value, "to_dict") else dict(value)
    payload = copy.deepcopy(payload)
    if not isinstance(payload.get("kind"), Enum):
        from core.runtime.runtime_memory_engine import RuntimeMemoryKind

        payload["kind"] = RuntimeMemoryKind(str(payload.get("kind")))
    for key in ("evidence_refs", "invariant_refs", "semantic_tags"):
        payload[key] = tuple(payload.get(key) or ())
    return payload


def _build_index(records: tuple[RuntimeMemoryRecord, ...], attr: str) -> dict[str, tuple[str, ...]]:
    index: dict[str, tuple[str, ...]] = {}
    for record in records:
        value = str(getattr(record, attr) or "")
        if not value:
            continue
        index[value] = tuple(dict.fromkeys([*index.get(value, ()), record.memory_id]))
    return dict(sorted(index.items()))


def _lineage_refs(records: tuple[RuntimeMemoryRecord, ...]) -> tuple[str, ...]:
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
