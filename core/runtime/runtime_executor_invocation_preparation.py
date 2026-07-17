from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Mapping


ZERO_RUNTIME_EXECUTOR_INVOCATION_PREPARATION_SCHEMA = (
    "zero.runtime.executor_invocation_preparation.v1"
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
)


@dataclass(frozen=True)
class ExecutorInvocationPreparationRecord:
    schema: str
    executor_invocation_preparation_id: str
    source_executor_adapter_attachment_id: str
    invocation_preparation_status: str
    executor_invocation_prepared: bool
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
    attachment: Mapping[str, Any],
    *,
    status: str,
    prepared: bool,
    denial_reason: str,
) -> dict[str, Any]:
    attachment_id = _text(attachment.get("executor_adapter_attachment_id"))
    preparation_id = ""
    if attachment_id:
        preparation_id = _stable_id("executor-invocation-preparation", attachment_id)

    return ExecutorInvocationPreparationRecord(
        schema=ZERO_RUNTIME_EXECUTOR_INVOCATION_PREPARATION_SCHEMA,
        executor_invocation_preparation_id=preparation_id,
        source_executor_adapter_attachment_id=attachment_id,
        invocation_preparation_status=status,
        executor_invocation_prepared=prepared,
        executor_invoked=False,
        execution_started=False,
        runtime_mutated=False,
        denial_reason=denial_reason,
        goal_id=_text(attachment.get("goal_id")),
        session_id=_text(attachment.get("session_id")),
        runtime_session_id=_text(attachment.get("runtime_session_id")),
        queue_id=_text(attachment.get("queue_id")),
        queue_entry_id=_text(attachment.get("queue_entry_id")),
        worker_id=_text(attachment.get("worker_id")),
        worker_claim_id=_text(attachment.get("worker_claim_id")),
        cycle_id=_text(attachment.get("cycle_id")),
        cycle_binding_id=_text(attachment.get("cycle_binding_id")),
        execution_request_id=_text(attachment.get("execution_request_id")),
        tick_id=_text(attachment.get("tick_id")),
        decision_id=_text(attachment.get("decision_id")),
        proposal_id=_text(attachment.get("proposal_id")),
        authorization_id=_text(attachment.get("authorization_id")),
        commit_id=_text(attachment.get("commit_id")),
        execution_admission_id=_text(attachment.get("execution_admission_id")),
        execution_permit_id=_text(attachment.get("execution_permit_id")),
        executor_envelope_id=_text(attachment.get("executor_envelope_id")),
        executor_adapter_binding_id=_text(attachment.get("executor_adapter_binding_id")),
        executor_adapter_attachment_id=attachment_id,
        adapter_name=_text(attachment.get("adapter_name")),
        adapter_metadata=_metadata(attachment.get("adapter_metadata")),
        capability_snapshot=_metadata(attachment.get("capability_snapshot")),
        execution_metadata=_metadata(attachment.get("execution_metadata")),
    ).to_dict()


def _has_required_lineage(attachment: Mapping[str, Any]) -> bool:
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
    )
    return all(_text(attachment.get(field)) for field in required)


def _is_duplicate(attachment_id: str, existing_preparations: Any) -> bool:
    for existing in existing_preparations or ():
        existing_map = _mapping(existing)
        if _text(existing_map.get("source_executor_adapter_attachment_id")) == attachment_id:
            return True
        if _text(existing_map.get("executor_adapter_attachment_id")) == attachment_id:
            return True
    return False


def evaluate_executor_invocation_preparation(
    executor_adapter_attachment_record: Any,
    *,
    existing_preparations: Any = None,
) -> dict[str, Any]:
    attachment = _mapping(executor_adapter_attachment_record)
    if not attachment:
        return _base_record(
            {},
            status="rejected",
            prepared=False,
            denial_reason="missing_executor_adapter_attachment",
        )

    attachment_id = _text(attachment.get("executor_adapter_attachment_id"))
    if _text(attachment.get("adapter_attachment_status")) != "attached":
        return _base_record(
            attachment,
            status="rejected",
            prepared=False,
            denial_reason="attachment_not_attached",
        )

    if attachment.get("executor_adapter_attached") is not True:
        return _base_record(
            attachment,
            status="rejected",
            prepared=False,
            denial_reason="adapter_not_attached",
        )

    if not _has_required_lineage(attachment):
        return _base_record(
            attachment,
            status="rejected",
            prepared=False,
            denial_reason="invalid_lineage",
        )

    if _is_duplicate(attachment_id, existing_preparations):
        return _base_record(
            attachment,
            status="rejected",
            prepared=False,
            denial_reason="duplicate_invocation_preparation",
        )

    return _base_record(
        attachment,
        status="prepared",
        prepared=True,
        denial_reason="",
    )


def submit_executor_invocation_preparation(
    executor_adapter_attachment_record: Any,
    *,
    existing_preparations: Any = None,
) -> dict[str, Any]:
    return evaluate_executor_invocation_preparation(
        executor_adapter_attachment_record,
        existing_preparations=existing_preparations,
    )


def summarize_executor_invocation_preparation(record: Any) -> dict[str, Any]:
    mapped = _mapping(record)
    return {
        "invocation_preparation_status": _text(mapped.get("invocation_preparation_status")) or "rejected",
        "executor_invocation_prepared": bool(mapped.get("executor_invocation_prepared") is True),
        "executor_invoked": False,
        "execution_started": False,
        "executor_invocation_preparation_id": _text(
            mapped.get("executor_invocation_preparation_id")
        ),
        "denial_reason": _text(mapped.get("denial_reason")),
    }


__all__ = [
    "ExecutorInvocationPreparationRecord",
    "ZERO_RUNTIME_EXECUTOR_INVOCATION_PREPARATION_SCHEMA",
    "evaluate_executor_invocation_preparation",
    "submit_executor_invocation_preparation",
    "summarize_executor_invocation_preparation",
]
