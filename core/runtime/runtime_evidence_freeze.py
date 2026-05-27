from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping


class RuntimeEvidenceKind(str, Enum):
    AUTHORITY = "authority"
    SURFACE = "surface"
    TRANSACTION = "transaction"
    REPLAY = "replay"
    RECOVERY = "recovery"
    REPAIR = "repair"
    AUDIT = "audit"
    SNAPSHOT = "snapshot"


@dataclass(frozen=True)
class RuntimeEvidenceRecord:
    evidence_id: str
    kind: RuntimeEvidenceKind
    task_id: str = ""
    step_id: str = ""
    trace_id: str = ""
    transaction_id: str = ""
    replay_run_id: str = ""
    recovery_attempt_id: str = ""
    authority_source: str = ""
    surface: str = ""
    decision: str = ""
    state: str = ""
    reason: str = ""
    refs: tuple[str, ...] = ()
    created_at: str = ""
    normalized_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        payload["refs"] = list(self.refs)
        return payload


@dataclass(frozen=True)
class RuntimeEvidenceSnapshot:
    snapshot_id: str
    evidence_ids: tuple[str, ...]
    authority_refs: tuple[str, ...] = ()
    surface_refs: tuple[str, ...] = ()
    transaction_refs: tuple[str, ...] = ()
    replay_refs: tuple[str, ...] = ()
    recovery_refs: tuple[str, ...] = ()
    repair_refs: tuple[str, ...] = ()
    audit_refs: tuple[str, ...] = ()
    created_at: str = ""
    normalized_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "evidence_ids",
            "authority_refs",
            "surface_refs",
            "transaction_refs",
            "replay_refs",
            "recovery_refs",
            "repair_refs",
            "audit_refs",
        ):
            payload[key] = list(getattr(self, key))
        return payload


_EVIDENCE: dict[str, RuntimeEvidenceRecord] = {}
_SNAPSHOTS: dict[str, RuntimeEvidenceSnapshot] = {}


def create_evidence_record(
    *,
    kind: RuntimeEvidenceKind | str,
    task_id: str = "",
    step_id: str = "",
    trace_id: str = "",
    transaction_id: str = "",
    replay_run_id: str = "",
    recovery_attempt_id: str = "",
    authority_source: str = "",
    surface: str = "",
    decision: str = "",
    state: str = "",
    reason: str = "",
    refs: Any = None,
) -> RuntimeEvidenceRecord:
    evidence_kind = RuntimeEvidenceKind(str(kind.value if isinstance(kind, RuntimeEvidenceKind) else kind))
    base = {
        "kind": evidence_kind.value,
        "task_id": str(task_id or ""),
        "step_id": str(step_id or ""),
        "trace_id": str(trace_id or ""),
        "transaction_id": str(transaction_id or ""),
        "replay_run_id": str(replay_run_id or ""),
        "recovery_attempt_id": str(recovery_attempt_id or ""),
        "authority_source": str(authority_source or ""),
        "surface": str(surface or ""),
        "decision": str(decision or ""),
        "state": str(state or ""),
        "reason": str(reason or ""),
        "refs": list(_text_tuple(refs)),
    }
    digest = _digest(base)
    record = RuntimeEvidenceRecord(
        evidence_id="runtime_evidence:" + digest[:16],
        kind=evidence_kind,
        task_id=base["task_id"],
        step_id=base["step_id"],
        trace_id=base["trace_id"],
        transaction_id=base["transaction_id"],
        replay_run_id=base["replay_run_id"],
        recovery_attempt_id=base["recovery_attempt_id"],
        authority_source=base["authority_source"],
        surface=base["surface"],
        decision=base["decision"],
        state=base["state"],
        reason=base["reason"],
        refs=tuple(base["refs"]),
        created_at=_now(),
        normalized_digest=digest,
    )
    _EVIDENCE[record.evidence_id] = record
    return record


def create_evidence_snapshot(records: Any) -> RuntimeEvidenceSnapshot:
    evidence_records = [_record_from_any(item) for item in _iter_records(records)]
    evidence_records = [item for item in evidence_records if item is not None]
    evidence_ids = tuple(record.evidence_id for record in evidence_records)
    authority_refs = tuple(record.evidence_id for record in evidence_records if record.kind is RuntimeEvidenceKind.AUTHORITY)
    surface_refs = tuple(record.evidence_id for record in evidence_records if record.kind is RuntimeEvidenceKind.SURFACE)
    transaction_refs = tuple(record.evidence_id for record in evidence_records if record.kind is RuntimeEvidenceKind.TRANSACTION)
    replay_refs = tuple(record.evidence_id for record in evidence_records if record.kind is RuntimeEvidenceKind.REPLAY)
    recovery_refs = tuple(record.evidence_id for record in evidence_records if record.kind is RuntimeEvidenceKind.RECOVERY)
    repair_refs = tuple(record.evidence_id for record in evidence_records if record.kind is RuntimeEvidenceKind.REPAIR)
    audit_refs = tuple(
        dict.fromkeys(
            [
                *(record.evidence_id for record in evidence_records if record.kind is RuntimeEvidenceKind.AUDIT),
                *(ref for record in evidence_records for ref in record.refs if str(ref).startswith("audit")),
            ]
        )
    )
    normalized = {
        "evidence_ids": list(evidence_ids),
        "authority_refs": list(authority_refs),
        "surface_refs": list(surface_refs),
        "transaction_refs": list(transaction_refs),
        "replay_refs": list(replay_refs),
        "recovery_refs": list(recovery_refs),
        "repair_refs": list(repair_refs),
        "audit_refs": list(audit_refs),
    }
    digest = _digest(normalized)
    snapshot = RuntimeEvidenceSnapshot(
        snapshot_id="runtime_evidence_snapshot:" + digest[:16],
        evidence_ids=evidence_ids,
        authority_refs=authority_refs,
        surface_refs=surface_refs,
        transaction_refs=transaction_refs,
        replay_refs=replay_refs,
        recovery_refs=recovery_refs,
        repair_refs=repair_refs,
        audit_refs=audit_refs,
        created_at=_now(),
        normalized_digest=digest,
    )
    _SNAPSHOTS[snapshot.snapshot_id] = snapshot
    return snapshot


def attach_authority_evidence(payload: Mapping[str, Any]) -> RuntimeEvidenceRecord:
    validation = payload.get("authority_validation") if isinstance(payload.get("authority_validation"), Mapping) else payload
    ok = bool(validation.get("ok")) if isinstance(validation, Mapping) else bool(payload.get("ok"))
    return create_evidence_record(
        kind=RuntimeEvidenceKind.AUTHORITY,
        task_id=str(payload.get("task_id") or ""),
        step_id=str(payload.get("step_id") or ""),
        trace_id=str(payload.get("trace_id") or ""),
        authority_source=str(payload.get("authority_source") or payload.get("source") or ""),
        surface=str(payload.get("surface") or payload.get("step_type") or ""),
        decision="allowed" if ok else "denied",
        state="allowed" if ok else "blocked",
        reason=str((validation.get("reason") if isinstance(validation, Mapping) else "") or payload.get("reason") or ""),
        refs=payload.get("audit_refs") or payload.get("refs"),
    )


def attach_surface_evidence(payload: Mapping[str, Any]) -> RuntimeEvidenceRecord:
    return create_evidence_record(
        kind=RuntimeEvidenceKind.SURFACE,
        surface=str(payload.get("name") or payload.get("surface") or payload.get("type") or ""),
        decision="requires_authority" if payload.get("requires_authority") else "authority_not_required",
        state="side_effect" if payload.get("side_effect") else "read_only",
        reason=str(payload.get("kind") or ""),
        refs=payload.get("refs"),
    )


def attach_transaction_evidence(payload: Mapping[str, Any] | Any) -> RuntimeEvidenceRecord:
    data = payload.to_dict() if hasattr(payload, "to_dict") else dict(payload)
    record = create_evidence_record(
        kind=RuntimeEvidenceKind.TRANSACTION,
        task_id=str(data.get("task_id") or ""),
        step_id=str(data.get("step_id") or ""),
        trace_id=str(data.get("trace_id") or ""),
        transaction_id=str(data.get("transaction_id") or ""),
        authority_source=str(data.get("authority_source") or ""),
        surface=str(data.get("surface") or ""),
        decision=str(data.get("decision") or data.get("state") or ""),
        state=str(data.get("state") or ""),
        reason=str(data.get("failure_result", {}).get("reason") if isinstance(data.get("failure_result"), Mapping) else data.get("reason") or ""),
        refs=data.get("audit_refs") or data.get("refs"),
    )
    return record


def attach_replay_evidence(payload: Mapping[str, Any] | Any) -> RuntimeEvidenceRecord:
    data = payload.to_dict() if hasattr(payload, "to_dict") else dict(payload)
    return create_evidence_record(
        kind=RuntimeEvidenceKind.REPLAY,
        trace_id=str(data.get("source_trace_id") or ""),
        transaction_id=",".join(str(item) for item in data.get("source_transaction_ids", []) if str(item or "").strip()),
        replay_run_id=str(data.get("replay_run_id") or ""),
        decision=str(data.get("mode") or ""),
        state=str(data.get("result_state") or ""),
        reason=str(data.get("failure_reason") or ""),
        refs=data.get("audit_refs"),
    )


def attach_recovery_evidence(payload: Mapping[str, Any] | Any) -> RuntimeEvidenceRecord:
    data = payload.to_dict() if hasattr(payload, "to_dict") else dict(payload)
    return create_evidence_record(
        kind=RuntimeEvidenceKind.RECOVERY,
        trace_id=str(data.get("original_trace_id") or ""),
        transaction_id=str(data.get("original_transaction_id") or data.get("recovery_transaction_id") or ""),
        replay_run_id=str(data.get("replay_run_id") or ""),
        recovery_attempt_id=str(data.get("recovery_attempt_id") or ""),
        decision=str(data.get("decision") or data.get("state") or ""),
        state=str(data.get("state") or ""),
        reason=str(data.get("failure_result", {}).get("reason") if isinstance(data.get("failure_result"), Mapping) else data.get("reason") or data.get("blocked_reason") or ""),
        refs=data.get("audit_refs"),
    )


def attach_repair_evidence(payload: Mapping[str, Any] | Any) -> RuntimeEvidenceRecord:
    data = payload.to_dict() if hasattr(payload, "to_dict") else dict(payload)
    return create_evidence_record(
        kind=RuntimeEvidenceKind.REPAIR,
        task_id=str(data.get("task_id") or ""),
        step_id=str(data.get("step_id") or ""),
        trace_id=str(data.get("trace_id") or ""),
        transaction_id=",".join(str(item) for item in data.get("transaction_refs", []) if str(item or "").strip()),
        replay_run_id=str(data.get("source_replay_run_id") or ""),
        recovery_attempt_id=str(data.get("source_recovery_attempt_id") or ""),
        decision=str(data.get("decision") or data.get("final_state") or ""),
        state=str(data.get("state") or data.get("final_state") or ""),
        reason=str(data.get("reason") or data.get("source_failure_id") or ""),
        refs=[str(data.get("loop_id") or "")],
    )


def normalize_evidence_record(record: RuntimeEvidenceRecord | Mapping[str, Any]) -> dict[str, Any]:
    payload = record.to_dict() if isinstance(record, RuntimeEvidenceRecord) else copy.deepcopy(dict(record))
    payload["created_at"] = "<normalized>"
    return _normalize_value(payload)


def normalize_evidence_snapshot(snapshot: RuntimeEvidenceSnapshot | Mapping[str, Any]) -> dict[str, Any]:
    payload = snapshot.to_dict() if isinstance(snapshot, RuntimeEvidenceSnapshot) else copy.deepcopy(dict(snapshot))
    payload["created_at"] = "<normalized>"
    return _normalize_value(payload)


def assert_evidence_lineage_valid(snapshot: RuntimeEvidenceSnapshot | Mapping[str, Any]) -> bool:
    payload = snapshot.to_dict() if isinstance(snapshot, RuntimeEvidenceSnapshot) else dict(snapshot)
    ordered_refs = [
        "authority_refs",
        "surface_refs",
        "transaction_refs",
        "replay_refs",
        "recovery_refs",
        "repair_refs",
        "audit_refs",
    ]
    positions = []
    evidence_ids = list(payload.get("evidence_ids") or [])
    for key in ordered_refs:
        refs = list(payload.get(key) or [])
        if refs:
            positions.append(min(evidence_ids.index(ref) for ref in refs if ref in evidence_ids))
    if positions != sorted(positions):
        raise AssertionError("evidence chain lineage order is invalid")
    return True


def assert_evidence_is_queryable(record: RuntimeEvidenceRecord | str) -> bool:
    item = get_evidence_record(record.evidence_id if isinstance(record, RuntimeEvidenceRecord) else record)
    if item is None:
        raise AssertionError("evidence record is not queryable")
    return True


def assert_evidence_does_not_grant_authority(record: RuntimeEvidenceRecord | Mapping[str, Any]) -> bool:
    payload = record.to_dict() if isinstance(record, RuntimeEvidenceRecord) else dict(record)
    forbidden = {"execution_authority", "authority_metadata", "execution_authority_metadata"}
    if forbidden & set(payload):
        _record_invariant_violation(
            "evidence.cannot_grant_authority",
            "evidence must not grant authority",
            payload,
        )
        raise AssertionError("evidence must not grant authority")
    if payload.get("authority_granted") or payload.get("approval_state") in {"approved", "allowed"}:
        _record_invariant_violation(
            "evidence.cannot_grant_authority",
            "evidence must not be treated as authority",
            payload,
        )
        raise AssertionError("evidence must not be treated as authority")
    return True


def get_evidence_record(evidence_id: str) -> RuntimeEvidenceRecord | None:
    return _EVIDENCE.get(str(evidence_id or ""))


def list_evidence_records(
    *,
    task_id: str | None = None,
    step_id: str | None = None,
    trace_id: str | None = None,
    transaction_id: str | None = None,
    replay_run_id: str | None = None,
    recovery_attempt_id: str | None = None,
) -> tuple[RuntimeEvidenceRecord, ...]:
    values = tuple(_EVIDENCE.values())
    if task_id is not None:
        values = tuple(item for item in values if item.task_id == task_id)
    if step_id is not None:
        values = tuple(item for item in values if item.step_id == step_id)
    if trace_id is not None:
        values = tuple(item for item in values if item.trace_id == trace_id)
    if transaction_id is not None:
        values = tuple(item for item in values if item.transaction_id == transaction_id)
    if replay_run_id is not None:
        values = tuple(item for item in values if item.replay_run_id == replay_run_id)
    if recovery_attempt_id is not None:
        values = tuple(item for item in values if item.recovery_attempt_id == recovery_attempt_id)
    return values


def evidence_refs_for_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    records = []
    if isinstance(payload.get("authority_decision"), Mapping):
        records.append(attach_authority_evidence(payload["authority_decision"]))
    if isinstance(payload.get("runtime_transaction"), Mapping) and payload["runtime_transaction"].get("transaction_id"):
        records.append(attach_transaction_evidence(payload["runtime_transaction"]))
    if isinstance(payload.get("runtime_replay"), Mapping):
        records.append(attach_replay_evidence(payload["runtime_replay"]))
    if isinstance(payload.get("runtime_recovery"), Mapping):
        records.append(attach_recovery_evidence(payload["runtime_recovery"]))
    if isinstance(payload.get("autonomous_repair_loop"), Mapping):
        records.append(attach_repair_evidence(payload["autonomous_repair_loop"]))
    snapshot = create_evidence_snapshot(records) if records else None
    memory_refs: dict[str, Any] = {}
    try:
        from core.runtime.runtime_memory_engine import memory_refs_for_payload

        memory_refs = memory_refs_for_payload({**dict(payload), "canonical_evidence": {"evidence_refs": [record.evidence_id for record in records]}})
    except Exception:
        memory_refs = {}
    return {
        "evidence_refs": [record.evidence_id for record in records],
        "evidence_snapshot": snapshot.to_dict() if snapshot else {},
        **memory_refs,
    }


def _record_from_any(value: Any) -> RuntimeEvidenceRecord | None:
    if isinstance(value, RuntimeEvidenceRecord):
        return value
    if isinstance(value, str):
        return get_evidence_record(value)
    if isinstance(value, Mapping):
        evidence_id = str(value.get("evidence_id") or "")
        if evidence_id and evidence_id in _EVIDENCE:
            return _EVIDENCE[evidence_id]
        if value.get("kind"):
            return create_evidence_record(
                kind=str(value.get("kind")),
                task_id=str(value.get("task_id") or ""),
                step_id=str(value.get("step_id") or ""),
                trace_id=str(value.get("trace_id") or ""),
                transaction_id=str(value.get("transaction_id") or ""),
                replay_run_id=str(value.get("replay_run_id") or ""),
                recovery_attempt_id=str(value.get("recovery_attempt_id") or ""),
                authority_source=str(value.get("authority_source") or ""),
                surface=str(value.get("surface") or ""),
                decision=str(value.get("decision") or ""),
                state=str(value.get("state") or ""),
                reason=str(value.get("reason") or ""),
                refs=value.get("refs"),
            )
    return None


def _iter_records(records: Any) -> list[Any]:
    if records is None:
        return []
    if isinstance(records, (RuntimeEvidenceRecord, str, Mapping)):
        return [records]
    try:
        return list(records)
    except TypeError:
        return [records]


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
        normalized = {}
        for key in sorted(value):
            if key in {"created_at", "updated_at", "timestamp", "started_at", "finished_at"}:
                continue
            normalized[str(key)] = _normalize_value(value[key])
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def _digest(value: Any) -> str:
    payload = json.dumps(_normalize_value(value), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _record_invariant_violation(invariant: str, reason: str, context: Mapping[str, Any]) -> None:
    try:
        from core.runtime.runtime_constitution_freeze import record_runtime_invariant_violation

        record_runtime_invariant_violation(
            invariant,
            component="evidence",
            reason=reason,
            context=context,
        )
    except Exception:
        pass
