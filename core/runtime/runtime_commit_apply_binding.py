from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Mapping


ZERO_RUNTIME_COMMIT_APPLY_BINDING_SCHEMA = (
    "zero.runtime.commit_apply_binding.v1"
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
class RuntimeCommitApplyRequest:
    commit_apply_id: str
    mutation_request_id: str
    execution_id: str
    changed_files: list[str]
    validation_passed: bool
    commit_allowed: bool
    rollback_required: bool
    lineage: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeCommitApplyResult:
    commit_apply_id: str
    mutation_request_id: str
    execution_id: str
    changed_files: list[str]
    validation_passed: bool
    commit_allowed: bool
    commit_applied: bool
    commit_recorded: bool
    commit_id: str
    git_diff_recorded: bool
    apply_status: str
    apply_reason: str
    rollback_required: bool
    safe_summary: dict[str, Any]

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


def _stable_id(prefix: str, *parts: Any) -> str:
    body = "|".join(_text(part) for part in parts if _text(part))
    digest = sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _lineage(mutation: Mapping[str, Any]) -> dict[str, str]:
    return {field: _text(mutation.get(field)) for field in LINEAGE_FIELDS}


def _request_lineage(mutation: Mapping[str, Any]) -> Mapping[str, Any]:
    request = _mapping(mutation.get("mutation_request"))
    return _mapping(request.get("lineage"))


def _lineage_matches(mutation: Mapping[str, Any]) -> bool:
    request_lineage = _request_lineage(mutation)
    if not request_lineage:
        return False
    for field in LINEAGE_FIELDS:
        if _text(request_lineage.get(field)) != _text(mutation.get(field)):
            return False
    return True


def _is_duplicate(mutation_request_id: str, existing: Any) -> bool:
    for item in existing or ():
        mapped = _mapping(item)
        if _text(mapped.get("mutation_request_id")) == mutation_request_id:
            return True
        request = _mapping(mapped.get("commit_apply_request"))
        if _text(request.get("mutation_request_id")) == mutation_request_id:
            return True
    return False


def _adapter_is_governed(adapter: Any) -> bool:
    if adapter is None:
        return False
    return (
        getattr(adapter, "safe_governed_commit_adapter", False) is True
        and callable(getattr(adapter, "record_commit_apply", None))
    )


def _commit_request(mutation: Mapping[str, Any]) -> dict[str, Any]:
    request = _mapping(mutation.get("mutation_request"))
    mutation_request_id = _text(request.get("mutation_request_id")) or _text(
        mutation.get("mutation_request_id")
    )
    execution_id = _text(request.get("execution_id")) or _text(
        mutation.get("execution_id")
    )
    commit_apply_id = _stable_id(
        "runtime-commit-apply",
        mutation_request_id,
        execution_id,
    )
    return RuntimeCommitApplyRequest(
        commit_apply_id=commit_apply_id,
        mutation_request_id=mutation_request_id,
        execution_id=execution_id,
        changed_files=[str(item) for item in mutation.get("changed_files") or []],
        validation_passed=bool(mutation.get("validation_passed") is True),
        commit_allowed=bool(mutation.get("commit_allowed") is True),
        rollback_required=bool(mutation.get("rollback_required") is True),
        lineage=_lineage(mutation),
    ).to_dict()


def _result(
    request: Mapping[str, Any],
    *,
    status: str,
    reason: str,
    commit_applied: bool = False,
    commit_recorded: bool = False,
    commit_id: str = "",
    git_diff_recorded: bool = False,
) -> dict[str, Any]:
    summary = {
        "runtime_commit_apply_status": status,
        "commit_apply_id": _text(request.get("commit_apply_id")),
        "mutation_request_id": _text(request.get("mutation_request_id")),
        "validation_passed": bool(request.get("validation_passed") is True),
        "commit_allowed": bool(request.get("commit_allowed") is True),
        "commit_applied": commit_applied,
        "commit_recorded": commit_recorded,
        "commit_id": _text(commit_id),
        "git_diff_recorded": git_diff_recorded,
        "rollback_required": bool(request.get("rollback_required") is True),
        "apply_reason": reason,
    }
    return RuntimeCommitApplyResult(
        commit_apply_id=_text(request.get("commit_apply_id")),
        mutation_request_id=_text(request.get("mutation_request_id")),
        execution_id=_text(request.get("execution_id")),
        changed_files=[str(item) for item in request.get("changed_files") or []],
        validation_passed=bool(request.get("validation_passed") is True),
        commit_allowed=bool(request.get("commit_allowed") is True),
        commit_applied=commit_applied,
        commit_recorded=commit_recorded,
        commit_id=_text(commit_id),
        git_diff_recorded=git_diff_recorded,
        apply_status=status,
        apply_reason=reason,
        rollback_required=bool(request.get("rollback_required") is True),
        safe_summary=summary,
    ).to_dict()


def _payload(
    *,
    request: Mapping[str, Any],
    result: Mapping[str, Any],
    records: list[dict[str, Any]] | None = None,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema": ZERO_RUNTIME_COMMIT_APPLY_BINDING_SCHEMA,
        "commit_apply_request": dict(request),
        "runtime_commit_apply_result": dict(result),
        "runtime_commit_apply_status": _text(result.get("apply_status")),
        "commit_apply_id": _text(result.get("commit_apply_id")),
        "mutation_request_id": _text(result.get("mutation_request_id")),
        "execution_id": _text(result.get("execution_id")),
        "changed_files": list(result.get("changed_files") or []),
        "validation_passed": bool(result.get("validation_passed") is True),
        "commit_allowed": bool(result.get("commit_allowed") is True),
        "commit_applied": bool(result.get("commit_applied") is True),
        "commit_recorded": bool(result.get("commit_recorded") is True),
        "commit_id": _text(result.get("commit_id")),
        "git_diff_recorded": bool(result.get("git_diff_recorded") is True),
        "apply_status": _text(result.get("apply_status")),
        "apply_reason": _text(result.get("apply_reason")),
        "rollback_required": bool(result.get("rollback_required") is True),
        "safe_summary": dict(result.get("safe_summary") or {}),
        "commit_apply_records": list(records or []),
        "non_mainline_issues": list(issues or []),
        "denial_reason": (
            ""
            if result.get("commit_applied") is True
            else _text(result.get("apply_reason"))
        ),
    }


def bind_runtime_commit_apply(
    runtime_controlled_mutation_result: Any,
    *,
    governed_commit_adapter: Any = None,
    existing_commit_applies: Any = None,
) -> dict[str, Any]:
    mutation = _mapping(runtime_controlled_mutation_result)
    request = _commit_request(mutation)
    if not mutation:
        result = _result(
            request,
            status="rejected",
            reason="missing_controlled_mutation_result",
        )
        return _payload(request=request, result=result)

    if mutation.get("mutation_allowed") is not True:
        result = _result(
            request,
            status="rejected",
            reason="mutation_not_allowed",
        )
        return _payload(request=request, result=result)

    if mutation.get("validation_passed") is not True:
        result = _result(
            request,
            status="rejected",
            reason="validation_not_passed",
        )
        return _payload(request=request, result=result)

    if mutation.get("commit_allowed") is not True:
        result = _result(
            request,
            status="rejected",
            reason="commit_not_allowed",
        )
        return _payload(request=request, result=result)

    if mutation.get("rollback_required") is True:
        result = _result(
            request,
            status="rejected",
            reason="rollback_required",
        )
        return _payload(request=request, result=result)

    if not _lineage_matches(mutation):
        result = _result(
            request,
            status="rejected",
            reason="lineage_mismatch",
        )
        return _payload(request=request, result=result)

    if _is_duplicate(request["mutation_request_id"], existing_commit_applies):
        result = _result(
            request,
            status="rejected",
            reason="duplicate_commit_apply",
        )
        return _payload(request=request, result=result)

    if not _adapter_is_governed(governed_commit_adapter):
        result = _result(
            request,
            status="blocked_no_governed_commit_adapter",
            reason="governed_commit_adapter_unavailable",
        )
        return _payload(request=request, result=result)

    try:
        raw_result = governed_commit_adapter.record_commit_apply(request)
    except Exception as exc:
        issue = f"governed_commit_adapter_failed:{exc.__class__.__name__}"
        result = _result(
            request,
            status="blocked_governed_commit_adapter_failed",
            reason=issue,
        )
        return _payload(request=request, result=result, issues=[issue])

    adapter_result = _mapping(raw_result)
    commit_applied = adapter_result.get("commit_applied") is True
    commit_recorded = adapter_result.get("commit_recorded") is True
    git_diff_recorded = adapter_result.get("git_diff_recorded") is True
    status = (
        "commit_apply_recorded"
        if commit_applied and commit_recorded and git_diff_recorded
        else "blocked_governed_commit_adapter_incomplete"
    )
    reason = (
        "governed_commit_apply_recorded"
        if status == "commit_apply_recorded"
        else "governed_commit_adapter_incomplete"
    )
    result = _result(
        request,
        status=status,
        reason=reason,
        commit_applied=commit_applied,
        commit_recorded=commit_recorded,
        commit_id=_text(adapter_result.get("commit_id")),
        git_diff_recorded=git_diff_recorded,
    )
    return _payload(
        request=request,
        result=result,
        issues=list(adapter_result.get("non_mainline_issues") or []),
    )


def submit_runtime_commit_apply(
    runtime_controlled_mutation_result: Any,
    *,
    governed_commit_adapter: Any = None,
    existing_commit_applies: Any = None,
) -> dict[str, Any]:
    apply_result = bind_runtime_commit_apply(
        runtime_controlled_mutation_result,
        governed_commit_adapter=governed_commit_adapter,
        existing_commit_applies=existing_commit_applies,
    )
    records = [dict(_mapping(item)) for item in existing_commit_applies or ()]
    if apply_result["runtime_commit_apply_status"] in {
        "commit_apply_recorded",
        "blocked_no_governed_commit_adapter",
        "blocked_governed_commit_adapter_failed",
        "blocked_governed_commit_adapter_incomplete",
    }:
        records.append(apply_result)
    return {
        "schema": ZERO_RUNTIME_COMMIT_APPLY_BINDING_SCHEMA + ".submit",
        "ok": apply_result["runtime_commit_apply_status"] == "commit_apply_recorded",
        "runtime_commit_apply_status": apply_result[
            "runtime_commit_apply_status"
        ],
        "runtime_commit_apply_result": apply_result,
        "commit_applied": apply_result["commit_applied"],
        "commit_recorded": apply_result["commit_recorded"],
        "commit_id": apply_result["commit_id"],
        "git_diff_recorded": apply_result["git_diff_recorded"],
        "commit_apply_records": records,
        "commit_apply_count": len(records),
        "denial_reason": apply_result["denial_reason"],
        "non_mainline_issues": apply_result["non_mainline_issues"],
    }


def build_runtime_commit_apply_state(records: Any) -> dict[str, Any]:
    items = [dict(_mapping(item)) for item in records or ()]
    latest = items[-1] if items else {}
    return {
        "schema": ZERO_RUNTIME_COMMIT_APPLY_BINDING_SCHEMA + ".state",
        "runtime_commit_apply_status": _text(
            latest.get("runtime_commit_apply_status")
        )
        or "rejected",
        "commit_applied": bool(latest.get("commit_applied") is True),
        "commit_recorded": bool(latest.get("commit_recorded") is True),
        "commit_id": _text(latest.get("commit_id")),
        "git_diff_recorded": bool(latest.get("git_diff_recorded") is True),
        "commit_apply_count": len(items),
        "commit_apply_records": items,
    }


__all__ = [
    "RuntimeCommitApplyRequest",
    "RuntimeCommitApplyResult",
    "ZERO_RUNTIME_COMMIT_APPLY_BINDING_SCHEMA",
    "bind_runtime_commit_apply",
    "build_runtime_commit_apply_state",
    "submit_runtime_commit_apply",
]
