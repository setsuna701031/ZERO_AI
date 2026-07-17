from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Mapping


ZERO_RUNTIME_CONTROLLED_REAL_EXECUTOR_UNLOCK_SCHEMA = (
    "zero.runtime.controlled_real_executor_unlock.v1"
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
class RuntimeControlledExecutorAdapterRequest:
    schema: str
    adapter_request_id: str
    closure_id: str
    execution_result_id: str
    execution_session_id: str
    dispatch_id: str
    invocation_id: str
    gate_id: str
    task_id: str
    package_id: str
    real_executor_enabled: bool
    mutation_allowed: bool
    repo_mutation_enabled: bool
    subprocess_allowed: bool
    lineage: dict[str, str]
    closure_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeControlledExecutorAdapterResult:
    schema: str
    adapter_result_id: str
    adapter_request_id: str
    closure_id: str
    execution_result_id: str
    adapter_status: str
    adapter_completed: bool
    real_executor_enabled: bool
    execution_real: bool
    mutation_allowed: bool
    repo_mutation_enabled: bool
    subprocess_allowed: bool
    output_summary: dict[str, Any]
    error_summary: dict[str, Any]
    non_mainline_issues: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeControlledRealExecutorUnlockResult:
    schema: str
    unlock_id: str
    adapter_request_id: str
    adapter_result_id: str
    closure_id: str
    execution_result_id: str
    execution_session_id: str
    dispatch_id: str
    invocation_id: str
    gate_id: str
    task_id: str
    package_id: str
    controlled_real_executor_unlock_status: str
    unlock_reason: str
    real_executor_ready: bool
    real_executor_enabled: bool
    execution_real: bool
    mutation_allowed: bool
    repo_mutation_enabled: bool
    subprocess_allowed: bool
    adapter_request: dict[str, Any]
    adapter_result: dict[str, Any]
    frozen_metadata: dict[str, Any]
    safe_summary: dict[str, Any]
    non_mainline_issues: list[str]
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


def _lineage(closure: Mapping[str, Any]) -> dict[str, str]:
    return {field: _text(closure.get(field)) for field in LINEAGE_FIELDS}


def _frozen_lineage(closure: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen = _mapping(closure.get("frozen_metadata"))
    return _mapping(frozen.get("lineage"))


def _has_required_lineage(closure: Mapping[str, Any]) -> bool:
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
    return all(_text(closure.get(field)) for field in required)


def _lineage_matches(closure: Mapping[str, Any]) -> bool:
    lineage = _frozen_lineage(closure)
    if not lineage:
        return False
    for field in LINEAGE_FIELDS:
        if _text(lineage.get(field)) != _text(closure.get(field)):
            return False
    return (
        _text(closure.get("invocation_id"))
        == _text(closure.get("executor_invocation_record_id"))
        and _text(closure.get("gate_id"))
        == _text(closure.get("executor_invocation_gate_id"))
    )


def _is_duplicate(closure: Mapping[str, Any], existing_unlocks: Any) -> bool:
    closure_id = _text(closure.get("closure_id"))
    execution_result_id = _text(closure.get("execution_result_id"))
    for existing in existing_unlocks or ():
        existing_map = _mapping(existing)
        if _text(existing_map.get("closure_id")) == closure_id:
            return True
        if _text(existing_map.get("execution_result_id")) == execution_result_id:
            return True
    return False


def _adapter_is_safe(adapter: Any) -> bool:
    if adapter is None:
        return False
    return (
        getattr(adapter, "safe_no_mutation_adapter", False) is True
        and callable(getattr(adapter, "execute_controlled_no_mutation", None))
    )


def _adapter_request(closure: Mapping[str, Any]) -> dict[str, Any]:
    closure_id = _text(closure.get("closure_id"))
    execution_result_id = _text(closure.get("execution_result_id"))
    adapter_request_id = _stable_id(
        "runtime-controlled-executor-adapter-request",
        closure_id,
        execution_result_id,
    )
    return RuntimeControlledExecutorAdapterRequest(
        schema=ZERO_RUNTIME_CONTROLLED_REAL_EXECUTOR_UNLOCK_SCHEMA + ".adapter_request",
        adapter_request_id=adapter_request_id,
        closure_id=closure_id,
        execution_result_id=execution_result_id,
        execution_session_id=_text(closure.get("execution_session_id")),
        dispatch_id=_text(closure.get("dispatch_id")),
        invocation_id=_text(closure.get("invocation_id")),
        gate_id=_text(closure.get("gate_id")),
        task_id=_text(closure.get("task_id")),
        package_id=_text(closure.get("package_id")),
        real_executor_enabled=True,
        mutation_allowed=False,
        repo_mutation_enabled=False,
        subprocess_allowed=False,
        lineage=_lineage(closure),
        closure_summary=_metadata(closure.get("safe_summary")),
    ).to_dict()


def _adapter_result(
    request: Mapping[str, Any],
    *,
    status: str,
    completed: bool,
    output_summary: Mapping[str, Any] | None = None,
    error_summary: Mapping[str, Any] | None = None,
    non_mainline_issues: list[str] | None = None,
) -> dict[str, Any]:
    adapter_request_id = _text(request.get("adapter_request_id"))
    closure_id = _text(request.get("closure_id"))
    execution_result_id = _text(request.get("execution_result_id"))
    adapter_result_id = ""
    if adapter_request_id:
        adapter_result_id = _stable_id(
            "runtime-controlled-executor-adapter-result",
            adapter_request_id,
            status,
        )
    return RuntimeControlledExecutorAdapterResult(
        schema=ZERO_RUNTIME_CONTROLLED_REAL_EXECUTOR_UNLOCK_SCHEMA + ".adapter_result",
        adapter_result_id=adapter_result_id,
        adapter_request_id=adapter_request_id,
        closure_id=closure_id,
        execution_result_id=execution_result_id,
        adapter_status=status,
        adapter_completed=completed,
        real_executor_enabled=completed,
        execution_real=completed,
        mutation_allowed=False,
        repo_mutation_enabled=False,
        subprocess_allowed=False,
        output_summary=dict(output_summary or {}),
        error_summary=dict(error_summary or {}),
        non_mainline_issues=list(non_mainline_issues or []),
    ).to_dict()


def _base_unlock(
    closure: Mapping[str, Any],
    *,
    status: str,
    reason: str,
    adapter_request: Mapping[str, Any] | None = None,
    adapter_result: Mapping[str, Any] | None = None,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    closure_id = _text(closure.get("closure_id"))
    execution_result_id = _text(closure.get("execution_result_id"))
    unlock_id = ""
    if closure_id or execution_result_id:
        unlock_id = _stable_id(
            "runtime-controlled-real-executor-unlock",
            closure_id,
            execution_result_id,
        )
    request = dict(adapter_request or {})
    result = dict(adapter_result or {})
    completed = result.get("adapter_completed") is True
    lineage = _lineage(closure)
    non_mainline_issues = list(issues or result.get("non_mainline_issues") or [])
    frozen_metadata = {
        "lineage": lineage,
        "closure_id": closure_id,
        "closure_status": _text(closure.get("closure_status")),
        "closure_frozen_metadata": _metadata(closure.get("frozen_metadata")),
        "adapter_request_id": _text(request.get("adapter_request_id")),
        "adapter_result_id": _text(result.get("adapter_result_id")),
        "controlled_real_executor_boundary_only": True,
        "mutation_allowed": False,
        "repo_mutation_enabled": False,
        "subprocess_allowed": False,
    }
    safe_summary = {
        "controlled_real_executor_unlock_status": status,
        "closure_id": closure_id,
        "execution_result_id": execution_result_id,
        "real_executor_ready": bool(closure.get("real_executor_ready") is True),
        "real_executor_enabled": completed,
        "execution_real": completed,
        "mutation_allowed": False,
        "repo_mutation_enabled": False,
        "subprocess_allowed": False,
        "unlock_reason": reason,
    }

    return RuntimeControlledRealExecutorUnlockResult(
        schema=ZERO_RUNTIME_CONTROLLED_REAL_EXECUTOR_UNLOCK_SCHEMA,
        unlock_id=unlock_id,
        adapter_request_id=_text(request.get("adapter_request_id")),
        adapter_result_id=_text(result.get("adapter_result_id")),
        closure_id=closure_id,
        execution_result_id=execution_result_id,
        execution_session_id=_text(closure.get("execution_session_id")),
        dispatch_id=_text(closure.get("dispatch_id")),
        invocation_id=_text(closure.get("invocation_id")),
        gate_id=_text(closure.get("gate_id")),
        task_id=_text(closure.get("task_id")),
        package_id=_text(closure.get("package_id")),
        controlled_real_executor_unlock_status=status,
        unlock_reason=reason,
        real_executor_ready=bool(closure.get("real_executor_ready") is True),
        real_executor_enabled=completed,
        execution_real=completed,
        mutation_allowed=False,
        repo_mutation_enabled=False,
        subprocess_allowed=False,
        adapter_request=request,
        adapter_result=result,
        frozen_metadata=frozen_metadata,
        safe_summary=safe_summary,
        non_mainline_issues=non_mainline_issues,
        denial_reason="" if completed else reason,
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


def unlock_controlled_real_executor(
    runtime_executor_runtime_closure: Any,
    *,
    safe_executor_adapter: Any = None,
    existing_unlocks: Any = None,
    runtime_operator_service_authorized: bool = False,
) -> dict[str, Any]:
    closure = _mapping(runtime_executor_runtime_closure)
    if not closure:
        return _base_unlock(
            {},
            status="rejected",
            reason="missing_closure_result",
        )

    if _text(closure.get("closure_status")) != "dry_run_runtime_closed":
        return _base_unlock(
            closure,
            status="rejected",
            reason="closure_not_dry_run_runtime_closed",
        )

    if closure.get("real_executor_ready") is not True:
        return _base_unlock(
            closure,
            status="rejected",
            reason="real_executor_not_ready",
        )

    if closure.get("mutation_allowed") is True:
        return _base_unlock(
            closure,
            status="rejected",
            reason="mutation_not_allowed",
        )

    if not _has_required_lineage(closure):
        return _base_unlock(
            closure,
            status="rejected",
            reason="missing_required_lineage",
        )

    if not _lineage_matches(closure):
        return _base_unlock(
            closure,
            status="rejected",
            reason="lineage_mismatch",
        )

    if _is_duplicate(closure, existing_unlocks):
        return _base_unlock(
            closure,
            status="rejected",
            reason="duplicate_controlled_real_executor_unlock",
        )

    if runtime_operator_service_authorized is not True:
        return _base_unlock(
            closure,
            status="rejected",
            reason="runtime_operator_service_required",
        )

    request = _adapter_request(closure)
    if not _adapter_is_safe(safe_executor_adapter):
        result = _adapter_result(
            request,
            status="blocked_no_safe_executor_adapter",
            completed=False,
            error_summary={"summary": "safe_no_mutation_adapter_unavailable"},
        )
        return _base_unlock(
            closure,
            status="blocked_no_safe_executor_adapter",
            reason="safe_no_mutation_adapter_unavailable",
            adapter_request=request,
            adapter_result=result,
        )

    try:
        raw_result = safe_executor_adapter.execute_controlled_no_mutation(request)
    except Exception as exc:
        issue = f"adapter_unavailable:{exc.__class__.__name__}"
        result = _adapter_result(
            request,
            status="blocked_executor_adapter_unavailable",
            completed=False,
            error_summary={"summary": issue},
            non_mainline_issues=[issue],
        )
        return _base_unlock(
            closure,
            status="blocked_executor_adapter_unavailable",
            reason="safe_no_mutation_adapter_failed",
            adapter_request=request,
            adapter_result=result,
            issues=[issue],
        )

    mapped_result = _mapping(raw_result)
    adapter_status = _text(mapped_result.get("adapter_status")) or _text(
        mapped_result.get("status")
    )
    completed = adapter_status in {"completed", "adapter_completed", "success"}
    completed = (
        completed
        and mapped_result.get("mutation_allowed") is not True
        and mapped_result.get("repo_mutation_enabled") is not True
    )
    result = _adapter_result(
        request,
        status="completed" if completed else "blocked_executor_adapter_incomplete",
        completed=completed,
        output_summary=_metadata(mapped_result.get("output_summary")),
        error_summary=_metadata(mapped_result.get("error_summary")),
        non_mainline_issues=list(mapped_result.get("non_mainline_issues") or []),
    )
    return _base_unlock(
        closure,
        status=(
            "controlled_real_executor_unlocked"
            if completed
            else "blocked_executor_adapter_incomplete"
        ),
        reason=(
            "controlled_safe_no_mutation_adapter_completed"
            if completed
            else "safe_no_mutation_adapter_incomplete"
        ),
        adapter_request=request,
        adapter_result=result,
    )


def submit_controlled_real_executor_unlock(
    runtime_executor_runtime_closure: Any,
    *,
    safe_executor_adapter: Any = None,
    existing_unlocks: Any = None,
    runtime_operator_service_authorized: bool = False,
) -> dict[str, Any]:
    unlock = unlock_controlled_real_executor(
        runtime_executor_runtime_closure,
        safe_executor_adapter=safe_executor_adapter,
        existing_unlocks=existing_unlocks,
        runtime_operator_service_authorized=runtime_operator_service_authorized,
    )
    unlocks = [dict(_mapping(item)) for item in existing_unlocks or ()]
    if unlock["controlled_real_executor_unlock_status"] in {
        "controlled_real_executor_unlocked",
        "blocked_no_safe_executor_adapter",
        "blocked_executor_adapter_unavailable",
        "blocked_executor_adapter_incomplete",
    }:
        unlocks.append(unlock)

    return {
        "schema": ZERO_RUNTIME_CONTROLLED_REAL_EXECUTOR_UNLOCK_SCHEMA + ".submit",
        "ok": unlock["controlled_real_executor_unlock_status"]
        == "controlled_real_executor_unlocked",
        "controlled_real_executor_result": unlock,
        "controlled_real_executor_unlock_status": unlock[
            "controlled_real_executor_unlock_status"
        ],
        "real_executor_ready": unlock["real_executor_ready"],
        "real_executor_enabled": unlock["real_executor_enabled"],
        "execution_real": unlock["execution_real"],
        "repo_mutation_enabled": False,
        "mutation_allowed": False,
        "subprocess_allowed": False,
        "unlocks": unlocks,
        "unlock_count": len(unlocks),
        "unlock_id": unlock["unlock_id"],
        "closure_id": unlock["closure_id"],
        "execution_result_id": unlock["execution_result_id"],
        "denial_reason": unlock["denial_reason"],
        "non_mainline_issues": unlock["non_mainline_issues"],
    }


def build_controlled_real_executor_unlock_state(unlocks: Any) -> dict[str, Any]:
    records = [dict(_mapping(item)) for item in unlocks or ()]
    successful = [
        item
        for item in records
        if item.get("controlled_real_executor_unlock_status")
        == "controlled_real_executor_unlocked"
    ]
    blocked = [
        item
        for item in records
        if item.get("controlled_real_executor_unlock_status")
        == "blocked_no_safe_executor_adapter"
    ]
    latest = records[-1] if records else {}
    status = _text(latest.get("controlled_real_executor_unlock_status")) or "rejected"
    return {
        "schema": ZERO_RUNTIME_CONTROLLED_REAL_EXECUTOR_UNLOCK_SCHEMA + ".state",
        "controlled_real_executor_unlock_status": status,
        "real_executor_ready": bool(latest.get("real_executor_ready") is True),
        "real_executor_enabled": bool(successful),
        "execution_real": bool(successful),
        "repo_mutation_enabled": False,
        "mutation_allowed": False,
        "subprocess_allowed": False,
        "unlock_count": len(records),
        "successful_count": len(successful),
        "blocked_no_safe_adapter_count": len(blocked),
        "unlocked_execution_result_ids": [
            item.get("execution_result_id") or "" for item in successful
        ],
        "unlocks": records,
    }


__all__ = [
    "RuntimeControlledExecutorAdapterRequest",
    "RuntimeControlledExecutorAdapterResult",
    "RuntimeControlledRealExecutorUnlockResult",
    "ZERO_RUNTIME_CONTROLLED_REAL_EXECUTOR_UNLOCK_SCHEMA",
    "build_controlled_real_executor_unlock_state",
    "submit_controlled_real_executor_unlock",
    "unlock_controlled_real_executor",
]
