from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Mapping


ZERO_RUNTIME_EXECUTOR_INVOCATION_RECORD_SCHEMA = (
    "zero.runtime.executor_invocation_record.v1"
)


LINEAGE_FIELDS = (
    "goal_id",
    "session_id",
    "runtime_session_id",
    "queue_id",
    "queue_entry_id",
    "worker_id",
    "worker_claim_id",
    "cycle_id",
    "cycle_binding_id",
    "execution_request_id",
    "tick_id",
    "decision_id",
    "proposal_id",
    "authorization_id",
    "commit_id",
    "execution_admission_id",
    "execution_permit_id",
    "executor_envelope_id",
    "executor_adapter_binding_id",
    "executor_adapter_attachment_id",
    "executor_invocation_preparation_id",
    "executor_invocation_approval_id",
    "executor_invocation_gate_id",
)


@dataclass(frozen=True)
class ExecutorInvocationRecord:
    schema: str
    executor_invocation_record_id: str
    source_executor_invocation_gate_id: str
    invocation_record_status: str
    executor_invocation_recorded: bool
    executor_invoked: bool
    execution_started: bool
    runtime_mutated: bool
    denial_reason: str
    goal_id: str
    session_id: str
    runtime_session_id: str
    queue_id: str
    queue_entry_id: str
    worker_id: str
    worker_claim_id: str
    cycle_id: str
    cycle_binding_id: str
    execution_request_id: str
    tick_id: str
    decision_id: str
    proposal_id: str
    authorization_id: str
    commit_id: str
    execution_admission_id: str
    execution_permit_id: str
    executor_envelope_id: str
    executor_adapter_binding_id: str
    executor_adapter_attachment_id: str
    executor_invocation_preparation_id: str
    executor_invocation_approval_id: str
    executor_invocation_gate_id: str
    adapter_name: str
    adapter_metadata: dict[str, Any]
    capability_snapshot: dict[str, Any]
    execution_metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mapping(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return result
    return {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _metadata(value: Any) -> dict[str, Any]:
    mapped = _mapping(value)
    return dict(mapped) if mapped else {}


def _stable_id(prefix: str, *parts: Any) -> str:
    body = "|".join(_text(part) for part in parts if _text(part))
    digest = sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _base_record(
    gate: Mapping[str, Any],
    *,
    status: str,
    recorded: bool,
    denial_reason: str,
) -> dict[str, Any]:
    gate_id = _text(gate.get("executor_invocation_gate_id"))
    record_id = ""
    if gate_id:
        record_id = _stable_id("executor-invocation-record", gate_id)

    return ExecutorInvocationRecord(
        schema=ZERO_RUNTIME_EXECUTOR_INVOCATION_RECORD_SCHEMA,
        executor_invocation_record_id=record_id,
        source_executor_invocation_gate_id=gate_id,
        invocation_record_status=status,
        executor_invocation_recorded=recorded,
        executor_invoked=False,
        execution_started=False,
        runtime_mutated=False,
        denial_reason=denial_reason,
        goal_id=_text(gate.get("goal_id")),
        session_id=_text(gate.get("session_id")),
        runtime_session_id=_text(gate.get("runtime_session_id")),
        queue_id=_text(gate.get("queue_id")),
        queue_entry_id=_text(gate.get("queue_entry_id")),
        worker_id=_text(gate.get("worker_id")),
        worker_claim_id=_text(gate.get("worker_claim_id")),
        cycle_id=_text(gate.get("cycle_id")),
        cycle_binding_id=_text(gate.get("cycle_binding_id")),
        execution_request_id=_text(gate.get("execution_request_id")),
        tick_id=_text(gate.get("tick_id")),
        decision_id=_text(gate.get("decision_id")),
        proposal_id=_text(gate.get("proposal_id")),
        authorization_id=_text(gate.get("authorization_id")),
        commit_id=_text(gate.get("commit_id")),
        execution_admission_id=_text(gate.get("execution_admission_id")),
        execution_permit_id=_text(gate.get("execution_permit_id")),
        executor_envelope_id=_text(gate.get("executor_envelope_id")),
        executor_adapter_binding_id=_text(gate.get("executor_adapter_binding_id")),
        executor_adapter_attachment_id=_text(gate.get("executor_adapter_attachment_id")),
        executor_invocation_preparation_id=_text(
            gate.get("executor_invocation_preparation_id")
        ),
        executor_invocation_approval_id=_text(
            gate.get("executor_invocation_approval_id")
        ),
        executor_invocation_gate_id=gate_id,
        adapter_name=_text(gate.get("adapter_name")),
        adapter_metadata=_metadata(gate.get("adapter_metadata")),
        capability_snapshot=_metadata(gate.get("capability_snapshot")),
        execution_metadata=_metadata(gate.get("execution_metadata")),
    ).to_dict()


def _has_required_lineage(gate: Mapping[str, Any]) -> bool:
    required = (
        "goal_id",
        "runtime_session_id",
        "queue_entry_id",
        "worker_claim_id",
        "cycle_binding_id",
        "execution_request_id",
        "tick_id",
        "decision_id",
        "proposal_id",
        "authorization_id",
        "commit_id",
        "execution_admission_id",
        "execution_permit_id",
        "executor_envelope_id",
        "executor_adapter_binding_id",
        "executor_adapter_attachment_id",
        "executor_invocation_preparation_id",
        "executor_invocation_approval_id",
        "executor_invocation_gate_id",
    )
    return all(_text(gate.get(field)) for field in required)


def _is_duplicate(gate_id: str, existing_records: Any) -> bool:
    for existing in existing_records or ():
        existing_map = _mapping(existing)
        if _text(existing_map.get("source_executor_invocation_gate_id")) == gate_id:
            return True
        if _text(existing_map.get("executor_invocation_gate_id")) == gate_id:
            return True
    return False


def evaluate_executor_invocation_record(
    executor_invocation_gate_record: Any,
    *,
    existing_records: Any = None,
) -> dict[str, Any]:
    gate = _mapping(executor_invocation_gate_record)
    if not gate:
        return _base_record(
            {},
            status="rejected",
            recorded=False,
            denial_reason="missing_executor_invocation_gate",
        )

    gate_id = _text(gate.get("executor_invocation_gate_id"))
    if _text(gate.get("invocation_gate_status")) != "opened":
        return _base_record(
            gate,
            status="rejected",
            recorded=False,
            denial_reason="gate_not_opened",
        )

    if gate.get("executor_invocation_gate_open") is not True:
        return _base_record(
            gate,
            status="rejected",
            recorded=False,
            denial_reason="invocation_gate_closed",
        )

    if not _has_required_lineage(gate):
        return _base_record(
            gate,
            status="rejected",
            recorded=False,
            denial_reason="invalid_lineage",
        )

    if _is_duplicate(gate_id, existing_records):
        return _base_record(
            gate,
            status="rejected",
            recorded=False,
            denial_reason="duplicate_invocation_record",
        )

    return _base_record(
        gate,
        status="recorded",
        recorded=True,
        denial_reason="",
    )


def submit_executor_invocation_record(
    executor_invocation_gate_record: Any,
    *,
    existing_records: Any = None,
) -> dict[str, Any]:
    record = evaluate_executor_invocation_record(
        executor_invocation_gate_record,
        existing_records=existing_records,
    )
    records = [dict(_mapping(item)) for item in existing_records or ()]
    if record["executor_invocation_recorded"]:
        records.append(record)

    return {
        "schema": ZERO_RUNTIME_EXECUTOR_INVOCATION_RECORD_SCHEMA + ".submit",
        "ok": record["executor_invocation_recorded"],
        "executor_invocation_record": record,
        "invocation_record_status": record["invocation_record_status"],
        "executor_invocation_recorded": record["executor_invocation_recorded"],
        "executor_invoked": False,
        "execution_started": False,
        "runtime_mutated": False,
        "records": records,
        "record_count": len(records),
        "executor_invocation_record_id": record["executor_invocation_record_id"],
        "executor_invocation_gate_id": record["executor_invocation_gate_id"],
        "denial_reason": record["denial_reason"],
    }


def build_runtime_executor_invocation_record_state(records: Any) -> dict[str, Any]:
    items = [dict(_mapping(item)) for item in records or ()]
    recorded = [
        item for item in items if item.get("invocation_record_status") == "recorded"
    ]
    return {
        "schema": ZERO_RUNTIME_EXECUTOR_INVOCATION_RECORD_SCHEMA + ".state",
        "invocation_record_status": "recorded" if recorded else "rejected",
        "executor_invocation_recorded": bool(recorded),
        "executor_invoked": False,
        "execution_started": False,
        "runtime_mutated": False,
        "record_count": len(items),
        "recorded_count": len(recorded),
        "recorded_executor_invocation_gate_ids": [
            item.get("executor_invocation_gate_id") or "" for item in recorded
        ],
        "records": items,
    }


def summarize_executor_invocation_record(record: Any) -> dict[str, Any]:
    mapped = _mapping(record)
    return {
        "invocation_record_status": _text(mapped.get("invocation_record_status"))
        or "rejected",
        "executor_invocation_recorded": bool(
            mapped.get("executor_invocation_recorded") is True
        ),
        "executor_invoked": False,
        "execution_started": False,
        "runtime_mutated": False,
        "executor_invocation_record_id": _text(
            mapped.get("executor_invocation_record_id")
        ),
        "denial_reason": _text(mapped.get("denial_reason")),
    }


__all__ = [
    "ExecutorInvocationRecord",
    "ZERO_RUNTIME_EXECUTOR_INVOCATION_RECORD_SCHEMA",
    "build_runtime_executor_invocation_record_state",
    "evaluate_executor_invocation_record",
    "submit_executor_invocation_record",
    "summarize_executor_invocation_record",
]
