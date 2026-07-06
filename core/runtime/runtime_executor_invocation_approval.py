from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Mapping


ZERO_RUNTIME_EXECUTOR_INVOCATION_APPROVAL_SCHEMA = (
    "zero.runtime.executor_invocation_approval.v1"
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
)


@dataclass(frozen=True)
class ExecutorInvocationApprovalRecord:
    schema: str
    executor_invocation_approval_id: str
    source_executor_invocation_preparation_id: str
    invocation_approval_status: str
    executor_invocation_approved: bool
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
    preparation: Mapping[str, Any],
    *,
    status: str,
    approved: bool,
    denial_reason: str,
) -> dict[str, Any]:
    preparation_id = _text(preparation.get("executor_invocation_preparation_id"))
    approval_id = ""
    if preparation_id:
        approval_id = _stable_id("executor-invocation-approval", preparation_id)

    return ExecutorInvocationApprovalRecord(
        schema=ZERO_RUNTIME_EXECUTOR_INVOCATION_APPROVAL_SCHEMA,
        executor_invocation_approval_id=approval_id,
        source_executor_invocation_preparation_id=preparation_id,
        invocation_approval_status=status,
        executor_invocation_approved=approved,
        executor_invoked=False,
        execution_started=False,
        runtime_mutated=False,
        denial_reason=denial_reason,
        goal_id=_text(preparation.get("goal_id")),
        session_id=_text(preparation.get("session_id")),
        runtime_session_id=_text(preparation.get("runtime_session_id")),
        queue_id=_text(preparation.get("queue_id")),
        queue_entry_id=_text(preparation.get("queue_entry_id")),
        worker_id=_text(preparation.get("worker_id")),
        worker_claim_id=_text(preparation.get("worker_claim_id")),
        cycle_id=_text(preparation.get("cycle_id")),
        cycle_binding_id=_text(preparation.get("cycle_binding_id")),
        execution_request_id=_text(preparation.get("execution_request_id")),
        tick_id=_text(preparation.get("tick_id")),
        decision_id=_text(preparation.get("decision_id")),
        proposal_id=_text(preparation.get("proposal_id")),
        authorization_id=_text(preparation.get("authorization_id")),
        commit_id=_text(preparation.get("commit_id")),
        execution_admission_id=_text(preparation.get("execution_admission_id")),
        execution_permit_id=_text(preparation.get("execution_permit_id")),
        executor_envelope_id=_text(preparation.get("executor_envelope_id")),
        executor_adapter_binding_id=_text(
            preparation.get("executor_adapter_binding_id")
        ),
        executor_adapter_attachment_id=_text(
            preparation.get("executor_adapter_attachment_id")
        ),
        executor_invocation_preparation_id=preparation_id,
        adapter_name=_text(preparation.get("adapter_name")),
        adapter_metadata=_metadata(preparation.get("adapter_metadata")),
        capability_snapshot=_metadata(preparation.get("capability_snapshot")),
        execution_metadata=_metadata(preparation.get("execution_metadata")),
    ).to_dict()


def _has_required_lineage(preparation: Mapping[str, Any]) -> bool:
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
    )
    return all(_text(preparation.get(field)) for field in required)


def _is_duplicate(preparation_id: str, existing_approvals: Any) -> bool:
    for existing in existing_approvals or ():
        existing_map = _mapping(existing)
        if (
            _text(existing_map.get("source_executor_invocation_preparation_id"))
            == preparation_id
        ):
            return True
        if _text(existing_map.get("executor_invocation_preparation_id")) == preparation_id:
            return True
    return False


def evaluate_executor_invocation_approval(
    executor_invocation_preparation_record: Any,
    *,
    existing_approvals: Any = None,
) -> dict[str, Any]:
    preparation = _mapping(executor_invocation_preparation_record)
    if not preparation:
        return _base_record(
            {},
            status="rejected",
            approved=False,
            denial_reason="missing_executor_invocation_preparation",
        )

    preparation_id = _text(preparation.get("executor_invocation_preparation_id"))
    if _text(preparation.get("invocation_preparation_status")) != "prepared":
        return _base_record(
            preparation,
            status="rejected",
            approved=False,
            denial_reason="preparation_not_prepared",
        )

    if preparation.get("executor_invocation_prepared") is not True:
        return _base_record(
            preparation,
            status="rejected",
            approved=False,
            denial_reason="invocation_not_prepared",
        )

    if not _has_required_lineage(preparation):
        return _base_record(
            preparation,
            status="rejected",
            approved=False,
            denial_reason="invalid_lineage",
        )

    if _is_duplicate(preparation_id, existing_approvals):
        return _base_record(
            preparation,
            status="rejected",
            approved=False,
            denial_reason="duplicate_invocation_approval",
        )

    return _base_record(
        preparation,
        status="approved",
        approved=True,
        denial_reason="",
    )


def submit_executor_invocation_approval(
    executor_invocation_preparation_record: Any,
    *,
    existing_approvals: Any = None,
) -> dict[str, Any]:
    approval = evaluate_executor_invocation_approval(
        executor_invocation_preparation_record,
        existing_approvals=existing_approvals,
    )
    approvals = [dict(_mapping(item)) for item in existing_approvals or ()]
    if approval["executor_invocation_approved"]:
        approvals.append(approval)

    return {
        "schema": ZERO_RUNTIME_EXECUTOR_INVOCATION_APPROVAL_SCHEMA + ".submit",
        "ok": approval["executor_invocation_approved"],
        "executor_invocation_approval": approval,
        "invocation_approval_status": approval["invocation_approval_status"],
        "executor_invocation_approved": approval["executor_invocation_approved"],
        "executor_invoked": False,
        "execution_started": False,
        "runtime_mutated": False,
        "approvals": approvals,
        "approval_count": len(approvals),
        "executor_invocation_approval_id": approval[
            "executor_invocation_approval_id"
        ],
        "executor_invocation_preparation_id": approval[
            "executor_invocation_preparation_id"
        ],
        "denial_reason": approval["denial_reason"],
    }


def build_runtime_executor_invocation_approval_state(
    approvals: Any,
) -> dict[str, Any]:
    records = [dict(_mapping(item)) for item in approvals or ()]
    approved = [
        item
        for item in records
        if item.get("invocation_approval_status") == "approved"
    ]
    return {
        "schema": ZERO_RUNTIME_EXECUTOR_INVOCATION_APPROVAL_SCHEMA + ".state",
        "invocation_approval_status": "approved" if approved else "rejected",
        "executor_invocation_approved": bool(approved),
        "executor_invoked": False,
        "execution_started": False,
        "runtime_mutated": False,
        "approval_count": len(records),
        "approved_count": len(approved),
        "approved_executor_invocation_preparation_ids": [
            item.get("executor_invocation_preparation_id") or "" for item in approved
        ],
        "approvals": records,
    }


def summarize_executor_invocation_approval(record: Any) -> dict[str, Any]:
    mapped = _mapping(record)
    return {
        "invocation_approval_status": _text(mapped.get("invocation_approval_status"))
        or "rejected",
        "executor_invocation_approved": bool(
            mapped.get("executor_invocation_approved") is True
        ),
        "executor_invoked": False,
        "execution_started": False,
        "runtime_mutated": False,
        "executor_invocation_approval_id": _text(
            mapped.get("executor_invocation_approval_id")
        ),
        "denial_reason": _text(mapped.get("denial_reason")),
    }


__all__ = [
    "ExecutorInvocationApprovalRecord",
    "ZERO_RUNTIME_EXECUTOR_INVOCATION_APPROVAL_SCHEMA",
    "build_runtime_executor_invocation_approval_state",
    "evaluate_executor_invocation_approval",
    "submit_executor_invocation_approval",
    "summarize_executor_invocation_approval",
]
