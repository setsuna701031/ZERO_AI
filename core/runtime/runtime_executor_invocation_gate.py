from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Mapping


ZERO_RUNTIME_EXECUTOR_INVOCATION_GATE_SCHEMA = (
    "zero.runtime.executor_invocation_gate.v1"
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
)


@dataclass(frozen=True)
class ExecutorInvocationGateRecord:
    schema: str
    executor_invocation_gate_id: str
    source_executor_invocation_approval_id: str
    invocation_gate_status: str
    executor_invocation_gate_open: bool
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
    approval: Mapping[str, Any],
    *,
    status: str,
    opened: bool,
    denial_reason: str,
) -> dict[str, Any]:
    approval_id = _text(approval.get("executor_invocation_approval_id"))
    gate_id = ""
    if approval_id:
        gate_id = _stable_id("executor-invocation-gate", approval_id)

    return ExecutorInvocationGateRecord(
        schema=ZERO_RUNTIME_EXECUTOR_INVOCATION_GATE_SCHEMA,
        executor_invocation_gate_id=gate_id,
        source_executor_invocation_approval_id=approval_id,
        invocation_gate_status=status,
        executor_invocation_gate_open=opened,
        executor_invoked=False,
        execution_started=False,
        runtime_mutated=False,
        denial_reason=denial_reason,
        goal_id=_text(approval.get("goal_id")),
        session_id=_text(approval.get("session_id")),
        runtime_session_id=_text(approval.get("runtime_session_id")),
        queue_id=_text(approval.get("queue_id")),
        queue_entry_id=_text(approval.get("queue_entry_id")),
        worker_id=_text(approval.get("worker_id")),
        worker_claim_id=_text(approval.get("worker_claim_id")),
        cycle_id=_text(approval.get("cycle_id")),
        cycle_binding_id=_text(approval.get("cycle_binding_id")),
        execution_request_id=_text(approval.get("execution_request_id")),
        tick_id=_text(approval.get("tick_id")),
        decision_id=_text(approval.get("decision_id")),
        proposal_id=_text(approval.get("proposal_id")),
        authorization_id=_text(approval.get("authorization_id")),
        commit_id=_text(approval.get("commit_id")),
        execution_admission_id=_text(approval.get("execution_admission_id")),
        execution_permit_id=_text(approval.get("execution_permit_id")),
        executor_envelope_id=_text(approval.get("executor_envelope_id")),
        executor_adapter_binding_id=_text(approval.get("executor_adapter_binding_id")),
        executor_adapter_attachment_id=_text(
            approval.get("executor_adapter_attachment_id")
        ),
        executor_invocation_preparation_id=_text(
            approval.get("executor_invocation_preparation_id")
        ),
        executor_invocation_approval_id=approval_id,
        adapter_name=_text(approval.get("adapter_name")),
        adapter_metadata=_metadata(approval.get("adapter_metadata")),
        capability_snapshot=_metadata(approval.get("capability_snapshot")),
        execution_metadata=_metadata(approval.get("execution_metadata")),
    ).to_dict()


def _has_required_lineage(approval: Mapping[str, Any]) -> bool:
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
    )
    return all(_text(approval.get(field)) for field in required)


def _is_duplicate(approval_id: str, existing_gates: Any) -> bool:
    for existing in existing_gates or ():
        existing_map = _mapping(existing)
        if _text(existing_map.get("source_executor_invocation_approval_id")) == approval_id:
            return True
        if _text(existing_map.get("executor_invocation_approval_id")) == approval_id:
            return True
    return False


def evaluate_executor_invocation_gate(
    executor_invocation_approval_record: Any,
    *,
    existing_gates: Any = None,
) -> dict[str, Any]:
    approval = _mapping(executor_invocation_approval_record)
    if not approval:
        return _base_record(
            {},
            status="rejected",
            opened=False,
            denial_reason="missing_executor_invocation_approval",
        )

    approval_id = _text(approval.get("executor_invocation_approval_id"))
    if _text(approval.get("invocation_approval_status")) != "approved":
        return _base_record(
            approval,
            status="rejected",
            opened=False,
            denial_reason="approval_not_approved",
        )

    if approval.get("executor_invocation_approved") is not True:
        return _base_record(
            approval,
            status="rejected",
            opened=False,
            denial_reason="invocation_not_approved",
        )

    if not _has_required_lineage(approval):
        return _base_record(
            approval,
            status="rejected",
            opened=False,
            denial_reason="invalid_lineage",
        )

    if _is_duplicate(approval_id, existing_gates):
        return _base_record(
            approval,
            status="rejected",
            opened=False,
            denial_reason="duplicate_invocation_gate",
        )

    return _base_record(
        approval,
        status="opened",
        opened=True,
        denial_reason="",
    )


def submit_executor_invocation_gate(
    executor_invocation_approval_record: Any,
    *,
    existing_gates: Any = None,
) -> dict[str, Any]:
    gate = evaluate_executor_invocation_gate(
        executor_invocation_approval_record,
        existing_gates=existing_gates,
    )
    gates = [dict(_mapping(item)) for item in existing_gates or ()]
    if gate["executor_invocation_gate_open"]:
        gates.append(gate)

    return {
        "schema": ZERO_RUNTIME_EXECUTOR_INVOCATION_GATE_SCHEMA + ".submit",
        "ok": gate["executor_invocation_gate_open"],
        "executor_invocation_gate": gate,
        "invocation_gate_status": gate["invocation_gate_status"],
        "executor_invocation_gate_open": gate["executor_invocation_gate_open"],
        "executor_invoked": False,
        "execution_started": False,
        "runtime_mutated": False,
        "gates": gates,
        "gate_count": len(gates),
        "executor_invocation_gate_id": gate["executor_invocation_gate_id"],
        "executor_invocation_approval_id": gate["executor_invocation_approval_id"],
        "denial_reason": gate["denial_reason"],
    }


def build_runtime_executor_invocation_gate_state(gates: Any) -> dict[str, Any]:
    records = [dict(_mapping(item)) for item in gates or ()]
    opened = [
        item for item in records if item.get("invocation_gate_status") == "opened"
    ]
    return {
        "schema": ZERO_RUNTIME_EXECUTOR_INVOCATION_GATE_SCHEMA + ".state",
        "invocation_gate_status": "opened" if opened else "rejected",
        "executor_invocation_gate_open": bool(opened),
        "executor_invoked": False,
        "execution_started": False,
        "runtime_mutated": False,
        "gate_count": len(records),
        "opened_count": len(opened),
        "opened_executor_invocation_approval_ids": [
            item.get("executor_invocation_approval_id") or "" for item in opened
        ],
        "gates": records,
    }


def summarize_executor_invocation_gate(record: Any) -> dict[str, Any]:
    mapped = _mapping(record)
    return {
        "invocation_gate_status": _text(mapped.get("invocation_gate_status"))
        or "rejected",
        "executor_invocation_gate_open": bool(
            mapped.get("executor_invocation_gate_open") is True
        ),
        "executor_invoked": False,
        "execution_started": False,
        "runtime_mutated": False,
        "executor_invocation_gate_id": _text(
            mapped.get("executor_invocation_gate_id")
        ),
        "denial_reason": _text(mapped.get("denial_reason")),
    }


__all__ = [
    "ExecutorInvocationGateRecord",
    "ZERO_RUNTIME_EXECUTOR_INVOCATION_GATE_SCHEMA",
    "build_runtime_executor_invocation_gate_state",
    "evaluate_executor_invocation_gate",
    "submit_executor_invocation_gate",
    "summarize_executor_invocation_gate",
]
