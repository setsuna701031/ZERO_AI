from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Mapping


ZERO_RUNTIME_CONTROLLED_MUTATION_UNLOCK_SCHEMA = (
    "zero.runtime.controlled_mutation_unlock.v1"
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
class RuntimeControlledMutationRequest:
    execution_id: str
    executor_result_id: str
    mutation_request_id: str
    requested_changes: list[dict[str, Any]]
    authority_context: dict[str, Any]
    lineage: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeControlledMutationResult:
    mutation_allowed: bool
    mutation_started: bool
    mutation_completed: bool
    validation_passed: bool
    rollback_required: bool
    rollback_completed: bool
    commit_allowed: bool
    mutation_status: str
    mutation_reason: str
    changed_files: list[str]
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


def _lineage(unlock: Mapping[str, Any]) -> dict[str, str]:
    return {field: _text(unlock.get(field)) for field in LINEAGE_FIELDS}


def _frozen_lineage(unlock: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen = _mapping(unlock.get("frozen_metadata"))
    return _mapping(frozen.get("lineage"))


def _has_required_lineage(unlock: Mapping[str, Any]) -> bool:
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
    return all(_text(unlock.get(field)) for field in required)


def _lineage_matches(unlock: Mapping[str, Any]) -> bool:
    lineage = _frozen_lineage(unlock)
    if not lineage:
        return False
    for field in LINEAGE_FIELDS:
        if _text(lineage.get(field)) != _text(unlock.get(field)):
            return False
    return (
        _text(unlock.get("invocation_id"))
        == _text(unlock.get("executor_invocation_record_id"))
        and _text(unlock.get("gate_id"))
        == _text(unlock.get("executor_invocation_gate_id"))
    )


def _requested_changes(unlock: Mapping[str, Any]) -> list[dict[str, Any]]:
    adapter_result = _mapping(unlock.get("adapter_result"))
    output = _mapping(adapter_result.get("output_summary"))
    raw = output.get("requested_changes") or output.get("changes") or []
    if isinstance(raw, Mapping):
        raw = [raw]
    changes: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        mapped = _mapping(item)
        if mapped:
            changes.append(dict(mapped))
    if changes:
        return changes
    task_id = _text(unlock.get("task_id")) or "controlled-runtime-task"
    return [
        {
            "change_id": _stable_id("controlled-mutation-change", task_id),
            "path": "controlled/runtime/noop.txt",
            "operation": "governed_repo_edit",
            "source": "controlled_real_executor_result",
        }
    ]


def _authority_context(unlock: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "runtime_operator_service_owner": True,
        "governed_mutation_adapter_required": True,
        "repo_edit_sandbox_required": True,
        "rollback_required": True,
        "validation_required": True,
        "real_executor_enabled": bool(unlock.get("real_executor_enabled") is True),
        "execution_real": bool(unlock.get("execution_real") is True),
        "unlock_id": _text(unlock.get("unlock_id")),
        "adapter_result_id": _text(unlock.get("adapter_result_id")),
    }


def _direct_filesystem_requested(changes: list[dict[str, Any]]) -> bool:
    direct_operations = {
        "direct_write",
        "filesystem_write",
        "write_file_direct",
        "open_write",
        "executor_file_mutation",
    }
    direct_flags = (
        "direct_filesystem",
        "direct_filesystem_write",
        "executor_direct_write",
        "bypass_governed_adapter",
    )
    for change in changes:
        operation = _text(change.get("operation")).lower()
        if operation in direct_operations:
            return True
        if any(change.get(flag) is True for flag in direct_flags):
            return True
    return False


def _is_duplicate(request_id: str, executor_result_id: str, existing: Any) -> bool:
    for item in existing or ():
        mapped = _mapping(item)
        request = _mapping(mapped.get("mutation_request"))
        if _text(request.get("mutation_request_id")) == request_id:
            return True
        if _text(request.get("executor_result_id")) == executor_result_id:
            return True
    return False


def _adapter_is_governed(adapter: Any) -> bool:
    if adapter is None:
        return False
    return (
        getattr(adapter, "safe_governed_mutation_adapter", False) is True
        and callable(getattr(adapter, "execute_governed_mutation", None))
    )


def _request(unlock: Mapping[str, Any]) -> dict[str, Any]:
    execution_id = _text(unlock.get("unlock_id"))
    executor_result_id = _text(unlock.get("execution_result_id"))
    mutation_request_id = _stable_id(
        "runtime-controlled-mutation-request",
        execution_id,
        executor_result_id,
    )
    return RuntimeControlledMutationRequest(
        execution_id=execution_id,
        executor_result_id=executor_result_id,
        mutation_request_id=mutation_request_id,
        requested_changes=_requested_changes(unlock),
        authority_context=_authority_context(unlock),
        lineage=_lineage(unlock),
    ).to_dict()


def _result(
    *,
    status: str,
    reason: str,
    mutation_allowed: bool = False,
    mutation_started: bool = False,
    mutation_completed: bool = False,
    validation_passed: bool = False,
    rollback_required: bool = False,
    rollback_completed: bool = False,
    commit_allowed: bool = False,
    changed_files: list[str] | None = None,
    extra_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    summary = {
        "controlled_mutation_status": status,
        "mutation_allowed": mutation_allowed,
        "mutation_started": mutation_started,
        "mutation_completed": mutation_completed,
        "validation_passed": validation_passed,
        "rollback_required": rollback_required,
        "rollback_completed": rollback_completed,
        "commit_allowed": commit_allowed,
        "rollback_available": True,
        "validation_required": True,
        "autonomous_runtime_loop_closed": (
            mutation_allowed
            and mutation_started
            and mutation_completed
            and (validation_passed or rollback_completed)
        ),
        "mutation_reason": reason,
        **dict(extra_summary or {}),
    }
    return RuntimeControlledMutationResult(
        mutation_allowed=mutation_allowed,
        mutation_started=mutation_started,
        mutation_completed=mutation_completed,
        validation_passed=validation_passed,
        rollback_required=rollback_required,
        rollback_completed=rollback_completed,
        commit_allowed=commit_allowed,
        mutation_status=status,
        mutation_reason=reason,
        changed_files=list(changed_files or []),
        safe_summary=summary,
    ).to_dict()


def _base_payload(
    unlock: Mapping[str, Any],
    *,
    mutation_request: Mapping[str, Any] | None,
    mutation_result: Mapping[str, Any],
    issues: list[str] | None = None,
) -> dict[str, Any]:
    request = dict(mutation_request or {})
    result = dict(mutation_result)
    status = _text(result.get("mutation_status")) or "rejected"
    reason = _text(result.get("mutation_reason"))
    return {
        "schema": ZERO_RUNTIME_CONTROLLED_MUTATION_UNLOCK_SCHEMA,
        "controlled_mutation": bool(result.get("mutation_started") is True),
        "controlled_mutation_status": status,
        "mutation_request": request,
        "controlled_mutation_result": result,
        "execution_id": _text(request.get("execution_id")),
        "executor_result_id": _text(request.get("executor_result_id"))
        or _text(unlock.get("execution_result_id")),
        "mutation_request_id": _text(request.get("mutation_request_id")),
        "mutation_allowed": bool(result.get("mutation_allowed") is True),
        "mutation_started": bool(result.get("mutation_started") is True),
        "mutation_completed": bool(result.get("mutation_completed") is True),
        "validation_passed": bool(result.get("validation_passed") is True),
        "rollback_required": bool(result.get("rollback_required") is True),
        "rollback_completed": bool(result.get("rollback_completed") is True),
        "commit_allowed": bool(result.get("commit_allowed") is True),
        "rollback_available": True,
        "validation_required": True,
        "governed_mutation_adapter_attached": bool(
            _mapping(result.get("safe_summary")).get(
                "governed_mutation_adapter_attached"
            )
            is True
        ),
        "autonomous_runtime_loop_closed": bool(
            _mapping(result.get("safe_summary")).get("autonomous_runtime_loop_closed")
            is True
        ),
        "changed_files": list(result.get("changed_files") or []),
        "safe_summary": dict(result.get("safe_summary") or {}),
        "non_mainline_issues": list(issues or []),
        "denial_reason": "" if result.get("mutation_started") is True else reason,
        "goal_id": _text(unlock.get("goal_id")),
        "session_id": _text(unlock.get("session_id")),
        "runtime_session_id": _text(unlock.get("runtime_session_id")),
        "queue_id": _text(unlock.get("queue_id")),
        "queue_entry_id": _text(unlock.get("queue_entry_id")),
        "worker_id": _text(unlock.get("worker_id")),
        "worker_claim_id": _text(unlock.get("worker_claim_id")),
        "cycle_id": _text(unlock.get("cycle_id")),
        "cycle_binding_id": _text(unlock.get("cycle_binding_id")),
        "execution_request_id": _text(unlock.get("execution_request_id")),
        "tick_id": _text(unlock.get("tick_id")),
        "decision_id": _text(unlock.get("decision_id")),
        "proposal_id": _text(unlock.get("proposal_id")),
        "authorization_id": _text(unlock.get("authorization_id")),
        "commit_id": _text(unlock.get("commit_id")),
        "execution_admission_id": _text(unlock.get("execution_admission_id")),
        "execution_permit_id": _text(unlock.get("execution_permit_id")),
        "executor_envelope_id": _text(unlock.get("executor_envelope_id")),
        "executor_adapter_binding_id": _text(
            unlock.get("executor_adapter_binding_id")
        ),
        "executor_adapter_attachment_id": _text(
            unlock.get("executor_adapter_attachment_id")
        ),
        "executor_invocation_preparation_id": _text(
            unlock.get("executor_invocation_preparation_id")
        ),
        "executor_invocation_approval_id": _text(
            unlock.get("executor_invocation_approval_id")
        ),
        "executor_invocation_gate_id": _text(
            unlock.get("executor_invocation_gate_id")
        ),
        "executor_invocation_record_id": _text(
            unlock.get("executor_invocation_record_id")
        ),
        "execution_session_id": _text(unlock.get("execution_session_id")),
        "dispatch_id": _text(unlock.get("dispatch_id")),
        "execution_result_id": _text(unlock.get("execution_result_id")),
    }


def unlock_controlled_mutation(
    runtime_controlled_real_executor_unlock: Any,
    *,
    governed_mutation_adapter: Any = None,
    existing_mutations: Any = None,
    runtime_operator_service_authorized: bool = False,
) -> dict[str, Any]:
    unlock = _mapping(runtime_controlled_real_executor_unlock)
    if not unlock:
        return _base_payload(
            {},
            mutation_request=None,
            mutation_result=_result(
                status="rejected",
                reason="missing_executor_unlock",
            ),
        )

    if unlock.get("real_executor_enabled") is not True:
        return _base_payload(
            unlock,
            mutation_request=None,
            mutation_result=_result(
                status="rejected",
                reason="real_executor_not_enabled",
            ),
        )

    if unlock.get("execution_real") is not True:
        return _base_payload(
            unlock,
            mutation_request=None,
            mutation_result=_result(status="rejected", reason="execution_not_real"),
        )

    if not _has_required_lineage(unlock) or not _lineage_matches(unlock):
        return _base_payload(
            unlock,
            mutation_request=None,
            mutation_result=_result(status="rejected", reason="invalid_lineage"),
        )

    request = _request(unlock)
    if not request["authority_context"]:
        return _base_payload(
            unlock,
            mutation_request=request,
            mutation_result=_result(status="rejected", reason="missing_authority"),
        )

    if runtime_operator_service_authorized is not True:
        return _base_payload(
            unlock,
            mutation_request=request,
            mutation_result=_result(
                status="rejected",
                reason="runtime_operator_service_required",
            ),
        )

    if _direct_filesystem_requested(request["requested_changes"]):
        return _base_payload(
            unlock,
            mutation_request=request,
            mutation_result=_result(
                status="rejected",
                reason="direct_filesystem_mutation_forbidden",
            ),
        )

    if _is_duplicate(
        request["mutation_request_id"],
        request["executor_result_id"],
        existing_mutations,
    ):
        return _base_payload(
            unlock,
            mutation_request=request,
            mutation_result=_result(
                status="rejected",
                reason="duplicate_mutation_request",
            ),
        )

    if not _adapter_is_governed(governed_mutation_adapter):
        return _base_payload(
            unlock,
            mutation_request=request,
            mutation_result=_result(
                status="blocked_no_governed_mutation_adapter",
                reason="governed_mutation_adapter_unavailable",
            ),
        )

    try:
        raw_result = governed_mutation_adapter.execute_governed_mutation(request)
    except Exception as exc:
        issue = f"governed_mutation_adapter_failed:{exc.__class__.__name__}"
        return _base_payload(
            unlock,
            mutation_request=request,
            mutation_result=_result(
                status="blocked_governed_mutation_adapter_failed",
                reason=issue,
            ),
            issues=[issue],
        )

    adapter_result = _mapping(raw_result)
    mutation_started = adapter_result.get("mutation_started") is True
    validation_passed = adapter_result.get("validation_passed") is True
    rollback_completed = adapter_result.get("rollback_completed") is True
    changed_files = [str(item) for item in adapter_result.get("changed_files") or []]
    mutation_completed = bool(
        adapter_result.get("mutation_completed") is True
        or (mutation_started and (validation_passed or rollback_completed))
    )
    rollback_required = bool(
        adapter_result.get("rollback_required") is True
        or (mutation_started and not validation_passed)
    )
    if validation_passed:
        status = "controlled_mutation_commit_allowed"
        reason = "governed_mutation_validated_commit_allowed"
        commit_allowed = True
    elif rollback_required and rollback_completed:
        status = "controlled_mutation_rolled_back"
        reason = "validation_failed_rollback_completed"
        commit_allowed = False
    else:
        status = "blocked_controlled_mutation_incomplete"
        reason = "governed_mutation_incomplete"
        commit_allowed = False

    return _base_payload(
        unlock,
        mutation_request=request,
        mutation_result=_result(
            status=status,
            reason=reason,
            mutation_allowed=mutation_started,
            mutation_started=mutation_started,
            mutation_completed=mutation_completed,
            validation_passed=validation_passed,
            rollback_required=rollback_required,
            rollback_completed=rollback_completed,
            commit_allowed=commit_allowed,
            changed_files=changed_files,
            extra_summary={
                "governed_mutation_adapter": True,
                "governed_mutation_adapter_attached": True,
                "repo_edit_sandbox": True,
            },
        ),
        issues=list(adapter_result.get("non_mainline_issues") or []),
    )


def submit_controlled_mutation_unlock(
    runtime_controlled_real_executor_unlock: Any,
    *,
    governed_mutation_adapter: Any = None,
    existing_mutations: Any = None,
    runtime_operator_service_authorized: bool = False,
) -> dict[str, Any]:
    mutation = unlock_controlled_mutation(
        runtime_controlled_real_executor_unlock,
        governed_mutation_adapter=governed_mutation_adapter,
        existing_mutations=existing_mutations,
        runtime_operator_service_authorized=runtime_operator_service_authorized,
    )
    records = [dict(_mapping(item)) for item in existing_mutations or ()]
    if mutation["controlled_mutation_status"] in {
        "controlled_mutation_commit_allowed",
        "controlled_mutation_rolled_back",
        "blocked_no_governed_mutation_adapter",
        "blocked_governed_mutation_adapter_failed",
        "blocked_controlled_mutation_incomplete",
    }:
        records.append(mutation)
    return {
        "schema": ZERO_RUNTIME_CONTROLLED_MUTATION_UNLOCK_SCHEMA + ".submit",
        "ok": mutation["controlled_mutation_status"]
        == "controlled_mutation_commit_allowed",
        "controlled_mutation": mutation["controlled_mutation"],
        "controlled_mutation_status": mutation["controlled_mutation_status"],
        "controlled_mutation_result": mutation,
        "mutation_allowed": mutation["mutation_allowed"],
        "mutation_started": mutation["mutation_started"],
        "mutation_completed": mutation["mutation_completed"],
        "validation_passed": mutation["validation_passed"],
        "rollback_required": mutation["rollback_required"],
        "rollback_completed": mutation["rollback_completed"],
        "commit_allowed": mutation["commit_allowed"],
        "rollback_available": True,
        "validation_required": True,
        "governed_mutation_adapter_attached": mutation[
            "governed_mutation_adapter_attached"
        ],
        "autonomous_runtime_loop_closed": mutation["autonomous_runtime_loop_closed"],
        "changed_files": mutation["changed_files"],
        "mutations": records,
        "mutation_count": len(records),
        "denial_reason": mutation["denial_reason"],
        "non_mainline_issues": mutation["non_mainline_issues"],
    }


def build_controlled_mutation_state(mutations: Any) -> dict[str, Any]:
    records = [dict(_mapping(item)) for item in mutations or ()]
    latest = records[-1] if records else {}
    return {
        "schema": ZERO_RUNTIME_CONTROLLED_MUTATION_UNLOCK_SCHEMA + ".state",
        "controlled_mutation_status": _text(
            latest.get("controlled_mutation_status")
        )
        or "rejected",
        "controlled_mutation": bool(latest.get("controlled_mutation") is True),
        "mutation_allowed": bool(latest.get("mutation_allowed") is True),
        "mutation_started": bool(latest.get("mutation_started") is True),
        "mutation_completed": bool(latest.get("mutation_completed") is True),
        "validation_passed": bool(latest.get("validation_passed") is True),
        "rollback_required": bool(latest.get("rollback_required") is True),
        "rollback_completed": bool(latest.get("rollback_completed") is True),
        "commit_allowed": bool(latest.get("commit_allowed") is True),
        "rollback_available": True,
        "validation_required": True,
        "governed_mutation_adapter_attached": bool(
            latest.get("governed_mutation_adapter_attached") is True
        ),
        "autonomous_runtime_loop_closed": bool(
            latest.get("autonomous_runtime_loop_closed") is True
        ),
        "changed_files": list(latest.get("changed_files") or []),
        "mutation_count": len(records),
        "mutations": records,
    }


__all__ = [
    "RuntimeControlledMutationRequest",
    "RuntimeControlledMutationResult",
    "ZERO_RUNTIME_CONTROLLED_MUTATION_UNLOCK_SCHEMA",
    "build_controlled_mutation_state",
    "submit_controlled_mutation_unlock",
    "unlock_controlled_mutation",
]
