from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_EXECUTOR_ADAPTER_BINDING_SCHEMA = (
    "zero.runtime.executor_adapter_binding.v1"
)


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _stable_id(prefix: str, *parts: str) -> str:
    joined = "|".join(_text(part) for part in parts)
    fragment = sha256(joined.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}::{fragment}"


def build_runtime_executor_adapter_binding_request(
    executor_envelope: Any,
    *,
    adapter_name: Any = "dry_run_executor_adapter",
) -> dict[str, Any]:
    envelope = _mapping(executor_envelope)
    lineage = _mapping(envelope.get("lineage"))
    goal_id = _text(envelope.get("goal_id"))
    work_package_id = _text(envelope.get("work_package_id"))
    runtime_session_id = _text(envelope.get("runtime_session_id"))
    session_id = _text(envelope.get("session_id")) or runtime_session_id
    queue_entry_id = _text(envelope.get("queue_entry_id"))
    queue_id = _text(envelope.get("queue_id")) or queue_entry_id
    worker_claim_id = _text(envelope.get("worker_claim_id"))
    worker_id = _text(envelope.get("worker_id")) or worker_claim_id
    cycle_binding_id = _text(envelope.get("cycle_binding_id"))
    cycle_id = _text(envelope.get("cycle_id")) or cycle_binding_id
    execution_request_id = _text(envelope.get("execution_request_id"))
    tick_id = _text(envelope.get("tick_id"))
    decision_id = _text(envelope.get("decision_id"))
    proposal_id = _text(envelope.get("proposal_id"))
    authorization_id = _text(envelope.get("authorization_id"))
    commit_id = _text(envelope.get("commit_id"))
    execution_admission_id = _text(envelope.get("execution_admission_id"))
    execution_permit_id = _text(envelope.get("execution_permit_id"))
    executor_envelope_id = _text(envelope.get("executor_envelope_id"))
    adapter = _text(adapter_name) or "dry_run_executor_adapter"

    binding_lineage = {
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "session_id": session_id,
        "queue_entry_id": queue_entry_id,
        "queue_id": queue_id,
        "worker_claim_id": worker_claim_id,
        "worker_id": worker_id,
        "cycle_binding_id": cycle_binding_id,
        "cycle_id": cycle_id,
        "execution_request_id": execution_request_id,
        "tick_id": tick_id,
        "decision_id": decision_id,
        "proposal_id": proposal_id,
        "authorization_id": authorization_id,
        "commit_id": commit_id,
        "execution_admission_id": execution_admission_id,
        "execution_permit_id": execution_permit_id,
        "executor_envelope_id": executor_envelope_id,
    }
    expected_lineage = {
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "session_id": session_id,
        "queue_entry_id": queue_entry_id,
        "queue_id": queue_id,
        "worker_claim_id": worker_claim_id,
        "worker_id": worker_id,
        "cycle_binding_id": cycle_binding_id,
        "cycle_id": cycle_id,
        "execution_request_id": execution_request_id,
        "tick_id": tick_id,
        "decision_id": decision_id,
        "proposal_id": proposal_id,
        "authorization_id": authorization_id,
        "commit_id": commit_id,
        "execution_admission_id": execution_admission_id,
        "execution_permit_id": execution_permit_id,
    }

    if not envelope:
        denial = "missing_executor_envelope"
        created = False
    elif envelope.get("executor_envelope_prepared") is not True:
        denial = envelope.get("denial_reason") or "executor_envelope_not_prepared"
        created = False
    elif envelope.get("executor_envelope_status") != "prepared":
        denial = "executor_envelope_not_prepared"
        created = False
    elif not executor_envelope_id:
        denial = "missing_executor_envelope_id"
        created = False
    elif (
        not goal_id
        or not runtime_session_id
        or not queue_entry_id
        or not worker_claim_id
        or not cycle_binding_id
        or not execution_request_id
        or not tick_id
        or not decision_id
        or not proposal_id
        or not authorization_id
        or not commit_id
        or not execution_admission_id
        or not execution_permit_id
    ):
        denial = "missing_adapter_binding_lineage_identity"
        created = False
    elif lineage != expected_lineage:
        denial = "invalid_lineage"
        created = False
    else:
        denial = ""
        created = True

    binding_id = (
        _stable_id(
            "runtime-executor-adapter-binding",
            goal_id,
            runtime_session_id,
            execution_request_id,
            tick_id,
            decision_id,
            proposal_id,
            authorization_id,
            commit_id,
            execution_admission_id,
            execution_permit_id,
            executor_envelope_id,
            adapter,
        )
        if created
        else ""
    )

    return {
        "schema": RUNTIME_EXECUTOR_ADAPTER_BINDING_SCHEMA + ".request",
        "adapter_binding_request_created": created,
        "adapter_binding_id": binding_id,
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "session_id": session_id,
        "queue_entry_id": queue_entry_id,
        "queue_id": queue_id,
        "worker_claim_id": worker_claim_id,
        "worker_id": worker_id,
        "cycle_binding_id": cycle_binding_id,
        "cycle_id": cycle_id,
        "execution_request_id": execution_request_id,
        "tick_id": tick_id,
        "decision_id": decision_id,
        "proposal_id": proposal_id,
        "authorization_id": authorization_id,
        "commit_id": commit_id,
        "execution_admission_id": execution_admission_id,
        "execution_permit_id": execution_permit_id,
        "executor_envelope_id": executor_envelope_id,
        "adapter_binding_status": "rejected",
        "executor_adapter_bound": False,
        "executor_invoked": False,
        "lineage": binding_lineage,
        "adapter_metadata": {
            "adapter_name": adapter,
            "adapter_reference": "dry_run_adapter_reference",
            "adapter_kind": "metadata_only",
            "adapter_attached": False,
            "executor_invoked": False,
        },
        "adapter_capability_metadata": {
            "supports_dry_run": True,
            "supports_operator_visibility": True,
            "supports_execution_start": False,
            "supports_filesystem_mutation": False,
            "supports_repo_mutation": False,
            "supports_progress_mutation": False,
            "supports_cursor_advance": False,
        },
        "policy_metadata": {
            "adapter_binding_policy": "record_only_adapter_reference",
            "bound_means_executor_attached": False,
            "bound_means_execute": False,
            "operator_visible": True,
            "dry_run_compatible": True,
            "reason": "adapter_binding_metadata_only_no_executor_invocation",
        },
        "audit_fields": {
            "record_only": True,
            "source_executor_envelope_id": executor_envelope_id,
            "operator_visible": True,
        },
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "filesystem_mutated": False,
        "code_mutated": False,
        "repo_mutated": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "runtime_executed": False,
        "progress_memory_written": False,
        "progress_mutated": False,
        "scheduler_called": False,
        "executor_attached": False,
        "executor_invoked": False,
    }


def evaluate_runtime_executor_adapter_binding(
    binding_request: Any,
    *,
    existing_bindings: Any = None,
) -> dict[str, Any]:
    request = _mapping(binding_request)
    existing = [_mapping(item) for item in _list(existing_bindings)]

    if not request:
        denial = "missing_adapter_binding_request"
        bound = False
    elif request.get("adapter_binding_request_created") is not True:
        denial = request.get("denial_reason") or "adapter_binding_request_not_created"
        bound = False
    elif any(
        item.get("executor_envelope_id") == request.get("executor_envelope_id")
        or item.get("execution_permit_id") == request.get("execution_permit_id")
        or item.get("adapter_binding_id") == request.get("adapter_binding_id")
        for item in existing
    ):
        denial = "duplicate_executor_adapter_binding"
        bound = False
    else:
        denial = ""
        bound = True

    return {
        "schema": RUNTIME_EXECUTOR_ADAPTER_BINDING_SCHEMA,
        "executor_adapter_bound": bound,
        "adapter_binding_id": request.get("adapter_binding_id") or "",
        "goal_id": request.get("goal_id") or "",
        "work_package_id": request.get("work_package_id") or "",
        "runtime_session_id": request.get("runtime_session_id") or "",
        "session_id": request.get("session_id") or "",
        "queue_entry_id": request.get("queue_entry_id") or "",
        "queue_id": request.get("queue_id") or "",
        "worker_claim_id": request.get("worker_claim_id") or "",
        "worker_id": request.get("worker_id") or "",
        "cycle_binding_id": request.get("cycle_binding_id") or "",
        "cycle_id": request.get("cycle_id") or "",
        "execution_request_id": request.get("execution_request_id") or "",
        "tick_id": request.get("tick_id") or "",
        "decision_id": request.get("decision_id") or "",
        "proposal_id": request.get("proposal_id") or "",
        "authorization_id": request.get("authorization_id") or "",
        "commit_id": request.get("commit_id") or "",
        "execution_admission_id": request.get("execution_admission_id") or "",
        "execution_permit_id": request.get("execution_permit_id") or "",
        "executor_envelope_id": request.get("executor_envelope_id") or "",
        "adapter_binding_status": "bound" if bound else "rejected",
        "executor_invoked": False,
        "lineage": _mapping(request.get("lineage")),
        "adapter_metadata": _mapping(request.get("adapter_metadata")),
        "adapter_capability_metadata": _mapping(
            request.get("adapter_capability_metadata")
        ),
        "policy_metadata": _mapping(request.get("policy_metadata")),
        "audit_fields": _mapping(request.get("audit_fields")),
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "filesystem_mutated": False,
        "code_mutated": False,
        "repo_mutated": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "runtime_executed": False,
        "progress_memory_written": False,
        "progress_mutated": False,
        "scheduler_called": False,
        "executor_attached": False,
        "executor_invoked": False,
    }


def bind_runtime_executor_adapter(
    executor_envelope: Any,
    *,
    existing_bindings: Any = None,
    adapter_name: Any = "dry_run_executor_adapter",
) -> dict[str, Any]:
    binding_request = build_runtime_executor_adapter_binding_request(
        executor_envelope,
        adapter_name=adapter_name,
    )
    binding = evaluate_runtime_executor_adapter_binding(
        binding_request,
        existing_bindings=existing_bindings,
    )
    bindings = [_mapping(item) for item in _list(existing_bindings)]
    if binding["executor_adapter_bound"]:
        bindings.append(binding)

    return {
        "schema": RUNTIME_EXECUTOR_ADAPTER_BINDING_SCHEMA + ".submit",
        "ok": binding["executor_adapter_bound"],
        "adapter_binding_request": binding_request,
        "executor_adapter_binding": binding,
        "adapter_binding_status": binding["adapter_binding_status"],
        "executor_adapter_bound": binding["executor_adapter_bound"],
        "executor_invoked": False,
        "bindings": bindings,
        "binding_count": len(bindings),
        "adapter_binding_id": binding["adapter_binding_id"],
        "goal_id": binding["goal_id"],
        "work_package_id": binding["work_package_id"],
        "runtime_session_id": binding["runtime_session_id"],
        "session_id": binding["session_id"],
        "queue_entry_id": binding["queue_entry_id"],
        "queue_id": binding["queue_id"],
        "worker_claim_id": binding["worker_claim_id"],
        "worker_id": binding["worker_id"],
        "cycle_binding_id": binding["cycle_binding_id"],
        "cycle_id": binding["cycle_id"],
        "execution_request_id": binding["execution_request_id"],
        "tick_id": binding["tick_id"],
        "decision_id": binding["decision_id"],
        "proposal_id": binding["proposal_id"],
        "authorization_id": binding["authorization_id"],
        "commit_id": binding["commit_id"],
        "execution_admission_id": binding["execution_admission_id"],
        "execution_permit_id": binding["execution_permit_id"],
        "executor_envelope_id": binding["executor_envelope_id"],
        "adapter_metadata": binding["adapter_metadata"],
        "adapter_capability_metadata": binding["adapter_capability_metadata"],
        "policy_metadata": binding["policy_metadata"],
        "audit_fields": binding["audit_fields"],
        "denial_reason": binding["denial_reason"],
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "filesystem_mutated": False,
        "code_mutated": False,
        "repo_mutated": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "runtime_executed": False,
        "progress_memory_written": False,
        "progress_mutated": False,
        "scheduler_called": False,
        "executor_attached": False,
        "executor_invoked": False,
    }


def build_runtime_executor_adapter_binding_state(bindings: Any) -> dict[str, Any]:
    records = [_mapping(item) for item in _list(bindings)]
    bound = [item for item in records if item.get("adapter_binding_status") == "bound"]
    return {
        "schema": RUNTIME_EXECUTOR_ADAPTER_BINDING_SCHEMA + ".state",
        "adapter_binding_status": "bound" if bound else "rejected",
        "executor_adapter_bound": bool(bound),
        "executor_invoked": False,
        "binding_count": len(records),
        "bound_count": len(bound),
        "bound_executor_envelope_ids": [
            item.get("executor_envelope_id") or "" for item in bound
        ],
        "bindings": records,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "filesystem_mutated": False,
        "code_mutated": False,
        "repo_mutated": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "runtime_executed": False,
        "progress_memory_written": False,
        "progress_mutated": False,
        "scheduler_called": False,
        "executor_attached": False,
        "executor_invoked": False,
    }


__all__ = [
    "RUNTIME_EXECUTOR_ADAPTER_BINDING_SCHEMA",
    "build_runtime_executor_adapter_binding_request",
    "evaluate_runtime_executor_adapter_binding",
    "bind_runtime_executor_adapter",
    "build_runtime_executor_adapter_binding_state",
]
