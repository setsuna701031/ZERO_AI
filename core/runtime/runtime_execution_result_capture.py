from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Mapping


ZERO_RUNTIME_EXECUTION_RESULT_CAPTURE_SCHEMA = (
    "zero.runtime.execution_result_capture.v1"
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
)


@dataclass(frozen=True)
class RuntimeExecutionResultCapture:
    schema: str
    execution_result_id: str
    execution_session_id: str
    dispatch_id: str
    invocation_id: str
    gate_id: str
    task_id: str
    package_id: str
    execution_started: bool
    execution_completed: bool
    result_recorded: bool
    dry_run: bool
    mutation_allowed: bool
    result_status: str
    result_reason: str
    output_summary: dict[str, Any]
    error_summary: dict[str, Any]
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


def _lineage(session: Mapping[str, Any]) -> dict[str, str]:
    return {field: _text(session.get(field)) for field in LINEAGE_FIELDS}


def _has_required_lineage(session: Mapping[str, Any]) -> bool:
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
    )
    return all(_text(session.get(field)) for field in required)


def _lineage_matches(session: Mapping[str, Any]) -> bool:
    return (
        _text(session.get("invocation_id"))
        == _text(session.get("executor_invocation_record_id"))
        and _text(session.get("gate_id"))
        == _text(session.get("executor_invocation_gate_id"))
    )


def _is_duplicate(execution_session_id: str, existing_results: Any) -> bool:
    for existing in existing_results or ():
        existing_map = _mapping(existing)
        if _text(existing_map.get("execution_session_id")) == execution_session_id:
            return True
    return False


def _base_capture(
    session: Mapping[str, Any],
    *,
    status: str,
    completed: bool,
    recorded: bool,
    dry_run: bool,
    mutation_allowed: bool,
    reason: str,
) -> dict[str, Any]:
    execution_session_id = _text(session.get("execution_session_id"))
    dispatch_id = _text(session.get("dispatch_id"))
    invocation_id = _text(session.get("invocation_id"))
    gate_id = _text(session.get("gate_id"))
    execution_result_id = ""
    if execution_session_id:
        execution_result_id = _stable_id(
            "runtime-execution-result", execution_session_id
        )

    lineage = _lineage(session)
    output_summary = {
        "executor_output_present": False,
        "stdout_present": False,
        "stderr_present": False,
        "summary": "dry_run_no_executor_output",
    }
    error_summary = {
        "error_present": False,
        "summary": "",
    }
    frozen_metadata = {
        "lineage": lineage,
        "execution_session_id": execution_session_id,
        "dispatch_id": dispatch_id,
        "invocation_id": invocation_id,
        "gate_id": gate_id,
        "session_status": _text(session.get("execution_status")),
        "session_reason": _text(session.get("execution_reason")),
        "session_frozen_metadata": _metadata(session.get("frozen_metadata")),
        "dry_run": dry_run,
        "mutation_allowed": mutation_allowed,
        "real_execution_enabled": False,
        "executor_output_present": False,
    }
    safe_summary = {
        "runtime_execution_result_capture_status": status,
        "execution_result_id": execution_result_id,
        "execution_session_id": execution_session_id,
        "dispatch_id": dispatch_id,
        "invocation_id": invocation_id,
        "gate_id": gate_id,
        "execution_started": bool(session.get("execution_started") is True),
        "execution_completed": completed,
        "execution_result_recorded": recorded,
        "execution_dry_run": dry_run,
        "mutation_allowed": mutation_allowed,
        "result_reason": reason,
    }

    return RuntimeExecutionResultCapture(
        schema=ZERO_RUNTIME_EXECUTION_RESULT_CAPTURE_SCHEMA,
        execution_result_id=execution_result_id,
        execution_session_id=execution_session_id,
        dispatch_id=dispatch_id,
        invocation_id=invocation_id,
        gate_id=gate_id,
        task_id=_text(session.get("task_id")),
        package_id=_text(session.get("package_id")),
        execution_started=bool(session.get("execution_started") is True),
        execution_completed=completed,
        result_recorded=recorded,
        dry_run=dry_run,
        mutation_allowed=mutation_allowed,
        result_status=status,
        result_reason=reason,
        output_summary=output_summary,
        error_summary=error_summary,
        frozen_metadata=frozen_metadata,
        safe_summary=safe_summary,
        denial_reason="" if recorded else reason,
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


def capture_runtime_execution_result_dry_run(
    runtime_execution_session_start: Any,
    *,
    existing_results: Any = None,
) -> dict[str, Any]:
    session = _mapping(runtime_execution_session_start)
    if not session:
        return _base_capture(
            {},
            status="rejected",
            completed=False,
            recorded=False,
            dry_run=False,
            mutation_allowed=False,
            reason="missing_execution_session",
        )

    execution_session_id = _text(session.get("execution_session_id"))
    if session.get("execution_started") is not True:
        return _base_capture(
            session,
            status="rejected",
            completed=False,
            recorded=False,
            dry_run=bool(session.get("dry_run") is True),
            mutation_allowed=bool(session.get("mutation_allowed") is True),
            reason="execution_not_started",
        )

    if session.get("dry_run") is not True:
        return _base_capture(
            session,
            status="rejected",
            completed=False,
            recorded=False,
            dry_run=False,
            mutation_allowed=bool(session.get("mutation_allowed") is True),
            reason="dry_run_required",
        )

    if session.get("mutation_allowed") is True:
        return _base_capture(
            session,
            status="rejected",
            completed=False,
            recorded=False,
            dry_run=True,
            mutation_allowed=True,
            reason="mutation_not_allowed",
        )

    if not _has_required_lineage(session) or not _lineage_matches(session):
        return _base_capture(
            session,
            status="rejected",
            completed=False,
            recorded=False,
            dry_run=True,
            mutation_allowed=False,
            reason="invalid_lineage",
        )

    if _is_duplicate(execution_session_id, existing_results):
        return _base_capture(
            session,
            status="rejected",
            completed=False,
            recorded=False,
            dry_run=True,
            mutation_allowed=False,
            reason="duplicate_execution_result_capture",
        )

    return _base_capture(
        session,
        status="dry_run_completed",
        completed=True,
        recorded=True,
        dry_run=True,
        mutation_allowed=False,
        reason="dry_run_result_recorded_no_executor_output",
    )


def submit_runtime_execution_result_capture(
    runtime_execution_session_start: Any,
    *,
    existing_results: Any = None,
) -> dict[str, Any]:
    result = capture_runtime_execution_result_dry_run(
        runtime_execution_session_start,
        existing_results=existing_results,
    )
    results = [dict(_mapping(item)) for item in existing_results or ()]
    if result["result_status"] == "dry_run_completed":
        results.append(result)

    return {
        "schema": ZERO_RUNTIME_EXECUTION_RESULT_CAPTURE_SCHEMA + ".submit",
        "ok": result["result_status"] == "dry_run_completed",
        "runtime_execution_result_capture": result,
        "runtime_execution_result_capture_status": result["result_status"],
        "result_status": result["result_status"],
        "result_reason": result["result_reason"],
        "execution_started": result["execution_started"],
        "execution_completed": result["execution_completed"],
        "execution_result_recorded": result["result_recorded"],
        "result_recorded": result["result_recorded"],
        "execution_dry_run": result["dry_run"],
        "dry_run": result["dry_run"],
        "mutation_allowed": result["mutation_allowed"],
        "results": results,
        "result_count": len(results),
        "execution_result_id": result["execution_result_id"],
        "execution_session_id": result["execution_session_id"],
        "dispatch_id": result["dispatch_id"],
        "invocation_id": result["invocation_id"],
        "gate_id": result["gate_id"],
        "denial_reason": result["denial_reason"],
    }


def build_runtime_execution_result_capture_state(results: Any) -> dict[str, Any]:
    records = [dict(_mapping(item)) for item in results or ()]
    completed = [
        item for item in records if item.get("result_status") == "dry_run_completed"
    ]
    return {
        "schema": ZERO_RUNTIME_EXECUTION_RESULT_CAPTURE_SCHEMA + ".state",
        "runtime_execution_result_capture_status": (
            "dry_run_completed" if completed else "rejected"
        ),
        "result_status": "dry_run_completed" if completed else "rejected",
        "execution_started": bool(completed),
        "execution_completed": bool(completed),
        "execution_result_recorded": bool(completed),
        "result_recorded": bool(completed),
        "execution_dry_run": bool(completed),
        "dry_run": bool(completed),
        "mutation_allowed": False,
        "result_count": len(records),
        "completed_count": len(completed),
        "completed_execution_session_ids": [
            item.get("execution_session_id") or "" for item in completed
        ],
        "results": records,
    }


def summarize_runtime_execution_result_capture(result: Any) -> dict[str, Any]:
    mapped = _mapping(result)
    return {
        "runtime_execution_result_capture_status": _text(
            mapped.get("result_status")
        )
        or "rejected",
        "execution_result_id": _text(mapped.get("execution_result_id")),
        "execution_session_id": _text(mapped.get("execution_session_id")),
        "dispatch_id": _text(mapped.get("dispatch_id")),
        "invocation_id": _text(mapped.get("invocation_id")),
        "gate_id": _text(mapped.get("gate_id")),
        "execution_completed": bool(mapped.get("execution_completed") is True),
        "execution_result_recorded": bool(mapped.get("result_recorded") is True),
        "execution_dry_run": bool(mapped.get("dry_run") is True),
        "mutation_allowed": False,
        "result_reason": _text(mapped.get("result_reason")),
    }


__all__ = [
    "RuntimeExecutionResultCapture",
    "ZERO_RUNTIME_EXECUTION_RESULT_CAPTURE_SCHEMA",
    "build_runtime_execution_result_capture_state",
    "capture_runtime_execution_result_dry_run",
    "submit_runtime_execution_result_capture",
    "summarize_runtime_execution_result_capture",
]
