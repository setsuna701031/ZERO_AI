from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Mapping


ZERO_RUNTIME_EXECUTOR_INVOCATION_DISPATCH_SCHEMA = (
    "zero.runtime.executor_invocation_dispatch.v1"
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
    "executor_invocation_record_id",
)


@dataclass(frozen=True)
class ExecutorInvocationDispatchResult:
    schema: str
    dispatch_id: str
    invocation_id: str
    gate_id: str
    package_id: str
    task_id: str
    executor_invoked: bool
    execution_started: bool
    dispatch_status: str
    dispatch_reason: str
    frozen_metadata: dict[str, Any]
    safe_summary: dict[str, Any]
    denial_reason: str
    runtime_mutated: bool
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
    executor_invocation_record_id: str

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


def _lineage(record: Mapping[str, Any]) -> dict[str, str]:
    return {field: _text(record.get(field)) for field in LINEAGE_FIELDS}


def _has_required_lineage(record: Mapping[str, Any]) -> bool:
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
        "executor_invocation_record_id",
    )
    return all(_text(record.get(field)) for field in required)


def _lineage_matches(record: Mapping[str, Any]) -> bool:
    source_gate_id = _text(record.get("source_executor_invocation_gate_id"))
    gate_id = _text(record.get("executor_invocation_gate_id"))
    return bool(source_gate_id and gate_id and source_gate_id == gate_id)


def _is_duplicate(invocation_id: str, existing_dispatches: Any) -> bool:
    for existing in existing_dispatches or ():
        existing_map = _mapping(existing)
        if _text(existing_map.get("invocation_id")) == invocation_id:
            return True
        if _text(existing_map.get("executor_invocation_record_id")) == invocation_id:
            return True
    return False


def _base_result(
    record: Mapping[str, Any],
    *,
    status: str,
    invoked: bool,
    reason: str,
) -> dict[str, Any]:
    invocation_id = _text(record.get("executor_invocation_record_id"))
    gate_id = _text(record.get("executor_invocation_gate_id"))
    dispatch_id = ""
    if invocation_id:
        dispatch_id = _stable_id("executor-invocation-dispatch", invocation_id)

    lineage = _lineage(record)
    package_id = _text(record.get("package_id")) or _text(record.get("work_package_id"))
    task_id = _text(record.get("task_id"))
    frozen_metadata = {
        "lineage": lineage,
        "adapter_name": _text(record.get("adapter_name")),
        "adapter_metadata": _metadata(record.get("adapter_metadata")),
        "capability_snapshot": _metadata(record.get("capability_snapshot")),
        "execution_metadata": _metadata(record.get("execution_metadata")),
        "dispatch_binding_only": True,
        "real_execution_enabled": False,
    }
    safe_summary = {
        "dispatch_status": status,
        "dispatch_reason": reason,
        "dispatch_id": dispatch_id,
        "invocation_id": invocation_id,
        "gate_id": gate_id,
        "executor_invoked": invoked,
        "execution_started": False,
    }

    return ExecutorInvocationDispatchResult(
        schema=ZERO_RUNTIME_EXECUTOR_INVOCATION_DISPATCH_SCHEMA,
        dispatch_id=dispatch_id,
        invocation_id=invocation_id,
        gate_id=gate_id,
        package_id=package_id,
        task_id=task_id,
        executor_invoked=invoked,
        execution_started=False,
        dispatch_status=status,
        dispatch_reason=reason,
        frozen_metadata=frozen_metadata,
        safe_summary=safe_summary,
        denial_reason="" if invoked else reason,
        runtime_mutated=False,
        goal_id=lineage["goal_id"],
        session_id=lineage["session_id"],
        runtime_session_id=lineage["runtime_session_id"],
        queue_id=lineage["queue_id"],
        queue_entry_id=lineage["queue_entry_id"],
        worker_id=lineage["worker_id"],
        worker_claim_id=lineage["worker_claim_id"],
        cycle_id=lineage["cycle_id"],
        cycle_binding_id=lineage["cycle_binding_id"],
        execution_request_id=lineage["execution_request_id"],
        tick_id=lineage["tick_id"],
        decision_id=lineage["decision_id"],
        proposal_id=lineage["proposal_id"],
        authorization_id=lineage["authorization_id"],
        commit_id=lineage["commit_id"],
        execution_admission_id=lineage["execution_admission_id"],
        execution_permit_id=lineage["execution_permit_id"],
        executor_envelope_id=lineage["executor_envelope_id"],
        executor_adapter_binding_id=lineage["executor_adapter_binding_id"],
        executor_adapter_attachment_id=lineage["executor_adapter_attachment_id"],
        executor_invocation_preparation_id=lineage[
            "executor_invocation_preparation_id"
        ],
        executor_invocation_approval_id=lineage["executor_invocation_approval_id"],
        executor_invocation_gate_id=lineage["executor_invocation_gate_id"],
        executor_invocation_record_id=lineage["executor_invocation_record_id"],
    ).to_dict()


def bind_executor_invocation_dispatch(
    executor_invocation_record: Any,
    *,
    existing_dispatches: Any = None,
) -> dict[str, Any]:
    record = _mapping(executor_invocation_record)
    if not record:
        return _base_result(
            {},
            status="rejected",
            invoked=False,
            reason="missing_executor_invocation_record",
        )

    invocation_id = _text(record.get("executor_invocation_record_id"))
    if _text(record.get("invocation_record_status")) != "recorded":
        return _base_result(
            record,
            status="rejected",
            invoked=False,
            reason="invocation_record_not_recorded",
        )

    if record.get("executor_invocation_recorded") is not True:
        return _base_result(
            record,
            status="rejected",
            invoked=False,
            reason="invocation_recorded_false",
        )

    if record.get("execution_started") is True:
        return _base_result(
            record,
            status="rejected",
            invoked=False,
            reason="execution_already_started",
        )

    if not _has_required_lineage(record) or not _lineage_matches(record):
        return _base_result(
            record,
            status="rejected",
            invoked=False,
            reason="invalid_lineage",
        )

    if _is_duplicate(invocation_id, existing_dispatches):
        return _base_result(
            record,
            status="rejected",
            invoked=False,
            reason="duplicate_invocation_dispatch",
        )

    return _base_result(
        record,
        status="dispatch_bound",
        invoked=True,
        reason="dispatch_binding_only_no_execution_start",
    )


def submit_executor_invocation_dispatch(
    executor_invocation_record: Any,
    *,
    existing_dispatches: Any = None,
) -> dict[str, Any]:
    dispatch = bind_executor_invocation_dispatch(
        executor_invocation_record,
        existing_dispatches=existing_dispatches,
    )
    dispatches = [dict(_mapping(item)) for item in existing_dispatches or ()]
    if dispatch["dispatch_status"] == "dispatch_bound":
        dispatches.append(dispatch)

    return {
        "schema": ZERO_RUNTIME_EXECUTOR_INVOCATION_DISPATCH_SCHEMA + ".submit",
        "ok": dispatch["dispatch_status"] == "dispatch_bound",
        "executor_invocation_dispatch": dispatch,
        "executor_invocation_dispatch_status": dispatch["dispatch_status"],
        "dispatch_status": dispatch["dispatch_status"],
        "dispatch_reason": dispatch["dispatch_reason"],
        "executor_invoked": dispatch["executor_invoked"],
        "execution_started": False,
        "runtime_mutated": False,
        "dispatches": dispatches,
        "dispatch_count": len(dispatches),
        "dispatch_id": dispatch["dispatch_id"],
        "invocation_id": dispatch["invocation_id"],
        "gate_id": dispatch["gate_id"],
        "denial_reason": dispatch["denial_reason"],
    }


def build_runtime_executor_invocation_dispatch_state(
    dispatches: Any,
) -> dict[str, Any]:
    records = [dict(_mapping(item)) for item in dispatches or ()]
    bound = [
        item for item in records if item.get("dispatch_status") == "dispatch_bound"
    ]
    return {
        "schema": ZERO_RUNTIME_EXECUTOR_INVOCATION_DISPATCH_SCHEMA + ".state",
        "executor_invocation_dispatch_status": (
            "dispatch_bound" if bound else "rejected"
        ),
        "dispatch_status": "dispatch_bound" if bound else "rejected",
        "executor_invoked": bool(bound),
        "execution_started": False,
        "runtime_mutated": False,
        "dispatch_count": len(records),
        "bound_count": len(bound),
        "bound_invocation_ids": [item.get("invocation_id") or "" for item in bound],
        "dispatches": records,
    }


def summarize_executor_invocation_dispatch(result: Any) -> dict[str, Any]:
    mapped = _mapping(result)
    return {
        "executor_invocation_dispatch_status": _text(
            mapped.get("dispatch_status")
        )
        or "rejected",
        "dispatch_id": _text(mapped.get("dispatch_id")),
        "invocation_id": _text(mapped.get("invocation_id")),
        "gate_id": _text(mapped.get("gate_id")),
        "executor_invoked": bool(mapped.get("executor_invoked") is True),
        "execution_started": False,
        "dispatch_reason": _text(mapped.get("dispatch_reason")),
    }


__all__ = [
    "ExecutorInvocationDispatchResult",
    "ZERO_RUNTIME_EXECUTOR_INVOCATION_DISPATCH_SCHEMA",
    "bind_executor_invocation_dispatch",
    "build_runtime_executor_invocation_dispatch_state",
    "submit_executor_invocation_dispatch",
    "summarize_executor_invocation_dispatch",
]
