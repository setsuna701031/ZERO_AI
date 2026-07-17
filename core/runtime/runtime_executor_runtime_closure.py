from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Mapping


ZERO_RUNTIME_EXECUTOR_RUNTIME_CLOSURE_SCHEMA = (
    "zero.runtime.executor_runtime_closure.v1"
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
    "execution_session_id",
    "dispatch_id",
    "execution_result_id",
)


@dataclass(frozen=True)
class RuntimeExecutionFeedbackRecord:
    feedback_id: str
    execution_result_id: str
    feedback_recorded: bool
    feedback_status: str
    feedback_reason: str
    dry_run: bool
    mutation_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeRecoveryFeedbackHandoff:
    recovery_handoff_id: str
    execution_result_id: str
    recovery_handoff_recorded: bool
    recovery_connected: bool
    recovery_status: str
    dry_run: bool
    mutation_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeMemoryFeedbackHandoff:
    memory_handoff_id: str
    execution_result_id: str
    memory_handoff_recorded: bool
    memory_connected: bool
    memory_status: str
    dry_run: bool
    mutation_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeExecutorReadinessStatus:
    readiness_id: str
    execution_result_id: str
    real_executor_ready: bool
    real_executor_enabled: bool
    readiness_status: str
    readiness_reason: str
    mutation_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeExecutorRuntimeClosureResult:
    schema: str
    closure_id: str
    execution_result_id: str
    execution_session_id: str
    dispatch_id: str
    invocation_id: str
    gate_id: str
    task_id: str
    package_id: str
    closure_status: str
    closure_reason: str
    feedback_recorded: bool
    recovery_handoff_recorded: bool
    memory_handoff_recorded: bool
    recovery_connected: bool
    memory_connected: bool
    real_executor_ready: bool
    real_executor_enabled: bool
    execution_dry_run: bool
    dry_run: bool
    mutation_allowed: bool
    execution_started: bool
    execution_completed: bool
    execution_result_recorded: bool
    feedback_record: dict[str, Any]
    recovery_handoff: dict[str, Any]
    memory_handoff: dict[str, Any]
    readiness_status: dict[str, Any]
    frozen_metadata: dict[str, Any]
    safe_summary: dict[str, Any]
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


def _lineage(result: Mapping[str, Any]) -> dict[str, str]:
    lineage = {field: _text(result.get(field)) for field in LINEAGE_FIELDS}
    lineage["execution_result_id"] = _text(result.get("execution_result_id"))
    return lineage


def _has_required_lineage(result: Mapping[str, Any]) -> bool:
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
        "execution_session_id",
        "dispatch_id",
        "execution_result_id",
    )
    return all(_text(result.get(field)) for field in required)


def _lineage_matches(result: Mapping[str, Any]) -> bool:
    return (
        _text(result.get("invocation_id"))
        == _text(result.get("executor_invocation_record_id"))
        and _text(result.get("gate_id"))
        == _text(result.get("executor_invocation_gate_id"))
    )


def _is_duplicate(execution_result_id: str, existing_closures: Any) -> bool:
    for existing in existing_closures or ():
        existing_map = _mapping(existing)
        if _text(existing_map.get("execution_result_id")) == execution_result_id:
            return True
    return False


def _feedback(execution_result_id: str, *, recorded: bool, dry_run: bool) -> dict[str, Any]:
    return RuntimeExecutionFeedbackRecord(
        feedback_id=_stable_id("runtime-execution-feedback", execution_result_id),
        execution_result_id=execution_result_id,
        feedback_recorded=recorded,
        feedback_status="recorded" if recorded else "rejected",
        feedback_reason=(
            "dry_run_execution_feedback_recorded"
            if recorded
            else "closure_rejected"
        ),
        dry_run=dry_run,
        mutation_allowed=False,
    ).to_dict()


def _recovery_handoff(
    execution_result_id: str, *, recorded: bool, dry_run: bool
) -> dict[str, Any]:
    return RuntimeRecoveryFeedbackHandoff(
        recovery_handoff_id=_stable_id("runtime-recovery-handoff", execution_result_id),
        execution_result_id=execution_result_id,
        recovery_handoff_recorded=recorded,
        recovery_connected=recorded,
        recovery_status="connected" if recorded else "rejected",
        dry_run=dry_run,
        mutation_allowed=False,
    ).to_dict()


def _memory_handoff(
    execution_result_id: str, *, recorded: bool, dry_run: bool
) -> dict[str, Any]:
    return RuntimeMemoryFeedbackHandoff(
        memory_handoff_id=_stable_id("runtime-memory-handoff", execution_result_id),
        execution_result_id=execution_result_id,
        memory_handoff_recorded=recorded,
        memory_connected=recorded,
        memory_status="connected" if recorded else "rejected",
        dry_run=dry_run,
        mutation_allowed=False,
    ).to_dict()


def _readiness(execution_result_id: str, *, ready: bool) -> dict[str, Any]:
    return RuntimeExecutorReadinessStatus(
        readiness_id=_stable_id("runtime-executor-readiness", execution_result_id),
        execution_result_id=execution_result_id,
        real_executor_ready=ready,
        real_executor_enabled=False,
        readiness_status="ready_disabled" if ready else "rejected",
        readiness_reason=(
            "dry_run_loop_closed_real_executor_readiness_only"
            if ready
            else "closure_rejected"
        ),
        mutation_allowed=False,
    ).to_dict()


def _base_closure(
    result: Mapping[str, Any],
    *,
    status: str,
    closed: bool,
    reason: str,
) -> dict[str, Any]:
    execution_result_id = _text(result.get("execution_result_id"))
    closure_id = ""
    if execution_result_id:
        closure_id = _stable_id("runtime-executor-runtime-closure", execution_result_id)

    dry_run = bool(result.get("dry_run") is True)
    lineage = _lineage(result)
    feedback = _feedback(execution_result_id, recorded=closed, dry_run=dry_run)
    recovery = _recovery_handoff(execution_result_id, recorded=closed, dry_run=dry_run)
    memory = _memory_handoff(execution_result_id, recorded=closed, dry_run=dry_run)
    readiness = _readiness(execution_result_id, ready=closed)
    frozen_metadata = {
        "lineage": lineage,
        "result_status": _text(result.get("result_status")),
        "result_reason": _text(result.get("result_reason")),
        "result_frozen_metadata": _metadata(result.get("frozen_metadata")),
        "dry_run": dry_run,
        "mutation_allowed": False,
        "real_executor_enabled": False,
        "closure_bundle": True,
    }
    safe_summary = {
        "runtime_executor_closure_status": status,
        "closure_id": closure_id,
        "execution_result_id": execution_result_id,
        "feedback_recorded": closed,
        "recovery_handoff_recorded": closed,
        "memory_handoff_recorded": closed,
        "recovery_connected": closed,
        "memory_connected": closed,
        "real_executor_ready": closed,
        "real_executor_enabled": False,
        "execution_dry_run": dry_run,
        "mutation_allowed": False,
    }

    return RuntimeExecutorRuntimeClosureResult(
        schema=ZERO_RUNTIME_EXECUTOR_RUNTIME_CLOSURE_SCHEMA,
        closure_id=closure_id,
        execution_result_id=execution_result_id,
        execution_session_id=_text(result.get("execution_session_id")),
        dispatch_id=_text(result.get("dispatch_id")),
        invocation_id=_text(result.get("invocation_id")),
        gate_id=_text(result.get("gate_id")),
        task_id=_text(result.get("task_id")),
        package_id=_text(result.get("package_id")),
        closure_status=status,
        closure_reason=reason,
        feedback_recorded=closed,
        recovery_handoff_recorded=closed,
        memory_handoff_recorded=closed,
        recovery_connected=closed,
        memory_connected=closed,
        real_executor_ready=closed,
        real_executor_enabled=False,
        execution_dry_run=dry_run,
        dry_run=dry_run,
        mutation_allowed=False,
        execution_started=bool(result.get("execution_started") is True),
        execution_completed=bool(result.get("execution_completed") is True),
        execution_result_recorded=bool(result.get("result_recorded") is True),
        feedback_record=feedback,
        recovery_handoff=recovery,
        memory_handoff=memory,
        readiness_status=readiness,
        frozen_metadata=frozen_metadata,
        safe_summary=safe_summary,
        denial_reason="" if closed else reason,
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


def close_executor_runtime_dry_run(
    runtime_execution_result_capture: Any,
    *,
    existing_closures: Any = None,
) -> dict[str, Any]:
    result = _mapping(runtime_execution_result_capture)
    if not result:
        return _base_closure(
            {},
            status="rejected",
            closed=False,
            reason="missing_execution_result_capture",
        )

    execution_result_id = _text(result.get("execution_result_id"))
    if result.get("execution_completed") is not True:
        return _base_closure(
            result,
            status="rejected",
            closed=False,
            reason="execution_not_completed",
        )

    if result.get("result_recorded") is not True:
        return _base_closure(
            result,
            status="rejected",
            closed=False,
            reason="execution_result_not_recorded",
        )

    if result.get("dry_run") is not True:
        return _base_closure(
            result,
            status="rejected",
            closed=False,
            reason="dry_run_required",
        )

    if result.get("mutation_allowed") is True:
        return _base_closure(
            result,
            status="rejected",
            closed=False,
            reason="mutation_not_allowed",
        )

    if not _has_required_lineage(result) or not _lineage_matches(result):
        return _base_closure(
            result,
            status="rejected",
            closed=False,
            reason="invalid_lineage",
        )

    if _is_duplicate(execution_result_id, existing_closures):
        return _base_closure(
            result,
            status="rejected",
            closed=False,
            reason="duplicate_executor_runtime_closure",
        )

    return _base_closure(
        result,
        status="dry_run_runtime_closed",
        closed=True,
        reason="dry_run_runtime_loop_closed_feedback_recovery_memory_ready",
    )


def submit_executor_runtime_closure(
    runtime_execution_result_capture: Any,
    *,
    existing_closures: Any = None,
) -> dict[str, Any]:
    closure = close_executor_runtime_dry_run(
        runtime_execution_result_capture,
        existing_closures=existing_closures,
    )
    closures = [dict(_mapping(item)) for item in existing_closures or ()]
    if closure["closure_status"] == "dry_run_runtime_closed":
        closures.append(closure)

    return {
        "schema": ZERO_RUNTIME_EXECUTOR_RUNTIME_CLOSURE_SCHEMA + ".submit",
        "ok": closure["closure_status"] == "dry_run_runtime_closed",
        "runtime_executor_closure": closure,
        "runtime_executor_closure_status": closure["closure_status"],
        "closure_status": closure["closure_status"],
        "closure_reason": closure["closure_reason"],
        "feedback_recorded": closure["feedback_recorded"],
        "recovery_handoff_recorded": closure["recovery_handoff_recorded"],
        "memory_handoff_recorded": closure["memory_handoff_recorded"],
        "recovery_connected": closure["recovery_connected"],
        "memory_connected": closure["memory_connected"],
        "real_executor_ready": closure["real_executor_ready"],
        "real_executor_enabled": False,
        "execution_dry_run": closure["execution_dry_run"],
        "dry_run": closure["dry_run"],
        "mutation_allowed": False,
        "closures": closures,
        "closure_count": len(closures),
        "closure_id": closure["closure_id"],
        "execution_result_id": closure["execution_result_id"],
        "denial_reason": closure["denial_reason"],
    }


def build_runtime_executor_closure_state(closures: Any) -> dict[str, Any]:
    records = [dict(_mapping(item)) for item in closures or ()]
    closed = [
        item
        for item in records
        if item.get("closure_status") == "dry_run_runtime_closed"
    ]
    return {
        "schema": ZERO_RUNTIME_EXECUTOR_RUNTIME_CLOSURE_SCHEMA + ".state",
        "runtime_executor_closure_status": (
            "dry_run_runtime_closed" if closed else "rejected"
        ),
        "closure_status": "dry_run_runtime_closed" if closed else "rejected",
        "feedback_recorded": bool(closed),
        "recovery_handoff_recorded": bool(closed),
        "memory_handoff_recorded": bool(closed),
        "recovery_connected": bool(closed),
        "memory_connected": bool(closed),
        "real_executor_ready": bool(closed),
        "real_executor_enabled": False,
        "execution_dry_run": bool(closed),
        "dry_run": bool(closed),
        "mutation_allowed": False,
        "closure_count": len(records),
        "closed_count": len(closed),
        "closed_execution_result_ids": [
            item.get("execution_result_id") or "" for item in closed
        ],
        "closures": records,
    }


__all__ = [
    "RuntimeExecutionFeedbackRecord",
    "RuntimeRecoveryFeedbackHandoff",
    "RuntimeMemoryFeedbackHandoff",
    "RuntimeExecutorReadinessStatus",
    "RuntimeExecutorRuntimeClosureResult",
    "ZERO_RUNTIME_EXECUTOR_RUNTIME_CLOSURE_SCHEMA",
    "build_runtime_executor_closure_state",
    "close_executor_runtime_dry_run",
    "submit_executor_runtime_closure",
]
