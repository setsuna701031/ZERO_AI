from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Mapping


ZERO_RUNTIME_EXECUTION_SESSION_START_SCHEMA = (
    "zero.runtime.execution_session_start.v1"
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
    "dispatch_id",
)


@dataclass(frozen=True)
class RuntimeExecutionSessionStartResult:
    schema: str
    execution_session_id: str
    dispatch_id: str
    invocation_id: str
    gate_id: str
    package_id: str
    task_id: str
    execution_started: bool
    dry_run: bool
    mutation_allowed: bool
    execution_status: str
    execution_reason: str
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


def _lineage(dispatch: Mapping[str, Any]) -> dict[str, str]:
    lineage = {field: _text(dispatch.get(field)) for field in LINEAGE_FIELDS}
    lineage["dispatch_id"] = _text(dispatch.get("dispatch_id"))
    return lineage


def _has_required_lineage(dispatch: Mapping[str, Any]) -> bool:
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
        "dispatch_id",
    )
    return all(_text(dispatch.get(field)) for field in required)


def _lineage_matches(dispatch: Mapping[str, Any]) -> bool:
    return (
        _text(dispatch.get("invocation_id"))
        == _text(dispatch.get("executor_invocation_record_id"))
        and _text(dispatch.get("gate_id"))
        == _text(dispatch.get("executor_invocation_gate_id"))
    )


def _is_duplicate(dispatch_id: str, existing_sessions: Any) -> bool:
    for existing in existing_sessions or ():
        existing_map = _mapping(existing)
        if _text(existing_map.get("dispatch_id")) == dispatch_id:
            return True
    return False


def _base_result(
    dispatch: Mapping[str, Any],
    *,
    status: str,
    started: bool,
    dry_run: bool,
    mutation_allowed: bool,
    reason: str,
) -> dict[str, Any]:
    dispatch_id = _text(dispatch.get("dispatch_id"))
    invocation_id = _text(dispatch.get("invocation_id"))
    gate_id = _text(dispatch.get("gate_id"))
    session_id = ""
    if dispatch_id:
        session_id = _stable_id("runtime-execution-session", dispatch_id)

    lineage = _lineage(dispatch)
    package_id = _text(dispatch.get("package_id"))
    task_id = _text(dispatch.get("task_id"))
    frozen_metadata = {
        "lineage": lineage,
        "dispatch_id": dispatch_id,
        "invocation_id": invocation_id,
        "gate_id": gate_id,
        "dispatch_status": _text(dispatch.get("dispatch_status")),
        "dispatch_reason": _text(dispatch.get("dispatch_reason")),
        "dispatch_frozen_metadata": _metadata(dispatch.get("frozen_metadata")),
        "dry_run": dry_run,
        "mutation_allowed": mutation_allowed,
        "real_execution_enabled": False,
    }
    safe_summary = {
        "runtime_execution_session_start_status": status,
        "execution_session_id": session_id,
        "dispatch_id": dispatch_id,
        "invocation_id": invocation_id,
        "gate_id": gate_id,
        "execution_started": started,
        "execution_dry_run": dry_run,
        "mutation_allowed": mutation_allowed,
        "execution_reason": reason,
    }

    return RuntimeExecutionSessionStartResult(
        schema=ZERO_RUNTIME_EXECUTION_SESSION_START_SCHEMA,
        execution_session_id=session_id,
        dispatch_id=dispatch_id,
        invocation_id=invocation_id,
        gate_id=gate_id,
        package_id=package_id,
        task_id=task_id,
        execution_started=started,
        dry_run=dry_run,
        mutation_allowed=mutation_allowed,
        execution_status=status,
        execution_reason=reason,
        frozen_metadata=frozen_metadata,
        safe_summary=safe_summary,
        denial_reason="" if started else reason,
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


def start_runtime_execution_session_dry_run(
    executor_invocation_dispatch_result: Any,
    *,
    dry_run: bool = True,
    mutation_allowed: bool = False,
    existing_sessions: Any = None,
) -> dict[str, Any]:
    dispatch = _mapping(executor_invocation_dispatch_result)
    if not dispatch:
        return _base_result(
            {},
            status="rejected",
            started=False,
            dry_run=dry_run,
            mutation_allowed=mutation_allowed,
            reason="missing_executor_invocation_dispatch",
        )

    dispatch_id = _text(dispatch.get("dispatch_id"))
    if dispatch.get("executor_invoked") is not True:
        return _base_result(
            dispatch,
            status="rejected",
            started=False,
            dry_run=dry_run,
            mutation_allowed=mutation_allowed,
            reason="executor_not_invoked",
        )

    if dispatch.get("execution_started") is True:
        return _base_result(
            dispatch,
            status="rejected",
            started=False,
            dry_run=dry_run,
            mutation_allowed=mutation_allowed,
            reason="dispatch_execution_already_started",
        )

    if dry_run is not True:
        return _base_result(
            dispatch,
            status="rejected",
            started=False,
            dry_run=False,
            mutation_allowed=mutation_allowed,
            reason="dry_run_required",
        )

    if mutation_allowed is True:
        return _base_result(
            dispatch,
            status="rejected",
            started=False,
            dry_run=True,
            mutation_allowed=True,
            reason="mutation_not_allowed",
        )

    if not _has_required_lineage(dispatch) or not _lineage_matches(dispatch):
        return _base_result(
            dispatch,
            status="rejected",
            started=False,
            dry_run=True,
            mutation_allowed=False,
            reason="invalid_lineage",
        )

    if _is_duplicate(dispatch_id, existing_sessions):
        return _base_result(
            dispatch,
            status="rejected",
            started=False,
            dry_run=True,
            mutation_allowed=False,
            reason="duplicate_execution_session_start",
        )

    return _base_result(
        dispatch,
        status="dry_run_started",
        started=True,
        dry_run=True,
        mutation_allowed=False,
        reason="dry_run_execution_session_started_no_mutation",
    )


def submit_runtime_execution_session_start(
    executor_invocation_dispatch_result: Any,
    *,
    dry_run: bool = True,
    mutation_allowed: bool = False,
    existing_sessions: Any = None,
) -> dict[str, Any]:
    session = start_runtime_execution_session_dry_run(
        executor_invocation_dispatch_result,
        dry_run=dry_run,
        mutation_allowed=mutation_allowed,
        existing_sessions=existing_sessions,
    )
    sessions = [dict(_mapping(item)) for item in existing_sessions or ()]
    if session["execution_status"] == "dry_run_started":
        sessions.append(session)

    return {
        "schema": ZERO_RUNTIME_EXECUTION_SESSION_START_SCHEMA + ".submit",
        "ok": session["execution_status"] == "dry_run_started",
        "runtime_execution_session_start": session,
        "runtime_execution_session_start_status": session["execution_status"],
        "execution_status": session["execution_status"],
        "execution_reason": session["execution_reason"],
        "execution_started": session["execution_started"],
        "execution_dry_run": session["dry_run"],
        "dry_run": session["dry_run"],
        "mutation_allowed": session["mutation_allowed"],
        "sessions": sessions,
        "session_count": len(sessions),
        "execution_session_id": session["execution_session_id"],
        "dispatch_id": session["dispatch_id"],
        "invocation_id": session["invocation_id"],
        "gate_id": session["gate_id"],
        "denial_reason": session["denial_reason"],
    }


def build_runtime_execution_session_start_state(sessions: Any) -> dict[str, Any]:
    records = [dict(_mapping(item)) for item in sessions or ()]
    started = [
        item for item in records if item.get("execution_status") == "dry_run_started"
    ]
    return {
        "schema": ZERO_RUNTIME_EXECUTION_SESSION_START_SCHEMA + ".state",
        "runtime_execution_session_start_status": (
            "dry_run_started" if started else "rejected"
        ),
        "execution_status": "dry_run_started" if started else "rejected",
        "execution_started": bool(started),
        "execution_dry_run": bool(started),
        "dry_run": bool(started),
        "mutation_allowed": False,
        "session_count": len(records),
        "started_count": len(started),
        "started_dispatch_ids": [item.get("dispatch_id") or "" for item in started],
        "sessions": records,
    }


def summarize_runtime_execution_session_start(result: Any) -> dict[str, Any]:
    mapped = _mapping(result)
    return {
        "runtime_execution_session_start_status": _text(
            mapped.get("execution_status")
        )
        or "rejected",
        "execution_session_id": _text(mapped.get("execution_session_id")),
        "dispatch_id": _text(mapped.get("dispatch_id")),
        "invocation_id": _text(mapped.get("invocation_id")),
        "gate_id": _text(mapped.get("gate_id")),
        "execution_started": bool(mapped.get("execution_started") is True),
        "execution_dry_run": bool(mapped.get("dry_run") is True),
        "mutation_allowed": False,
        "execution_reason": _text(mapped.get("execution_reason")),
    }


__all__ = [
    "RuntimeExecutionSessionStartResult",
    "ZERO_RUNTIME_EXECUTION_SESSION_START_SCHEMA",
    "build_runtime_execution_session_start_state",
    "start_runtime_execution_session_dry_run",
    "submit_runtime_execution_session_start",
    "summarize_runtime_execution_session_start",
]
