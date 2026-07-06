from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_EXECUTOR_ADAPTER_ATTACHMENT_SCHEMA = (
    "zero.runtime.executor_adapter_attachment.v1"
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


def build_runtime_executor_adapter_attachment_request(
    executor_adapter_binding: Any,
) -> dict[str, Any]:
    binding = _mapping(executor_adapter_binding)
    lineage = _mapping(binding.get("lineage"))
    goal_id = _text(binding.get("goal_id"))
    work_package_id = _text(binding.get("work_package_id"))
    runtime_session_id = _text(binding.get("runtime_session_id"))
    session_id = _text(binding.get("session_id")) or runtime_session_id
    queue_entry_id = _text(binding.get("queue_entry_id"))
    queue_id = _text(binding.get("queue_id")) or queue_entry_id
    worker_claim_id = _text(binding.get("worker_claim_id"))
    worker_id = _text(binding.get("worker_id")) or worker_claim_id
    cycle_binding_id = _text(binding.get("cycle_binding_id"))
    cycle_id = _text(binding.get("cycle_id")) or cycle_binding_id
    execution_request_id = _text(binding.get("execution_request_id"))
    tick_id = _text(binding.get("tick_id"))
    decision_id = _text(binding.get("decision_id"))
    proposal_id = _text(binding.get("proposal_id"))
    authorization_id = _text(binding.get("authorization_id"))
    commit_id = _text(binding.get("commit_id"))
    execution_admission_id = _text(binding.get("execution_admission_id"))
    execution_permit_id = _text(binding.get("execution_permit_id"))
    executor_envelope_id = _text(binding.get("executor_envelope_id"))
    executor_adapter_binding_id = _text(binding.get("adapter_binding_id"))

    attachment_lineage = {
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
        "executor_adapter_binding_id": executor_adapter_binding_id,
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
        "executor_envelope_id": executor_envelope_id,
    }

    if not binding:
        denial = "missing_executor_adapter_binding"
        created = False
    elif binding.get("executor_adapter_bound") is not True:
        denial = binding.get("denial_reason") or "executor_adapter_not_bound"
        created = False
    elif binding.get("adapter_binding_status") != "bound":
        denial = "executor_adapter_not_bound"
        created = False
    elif not executor_adapter_binding_id:
        denial = "missing_executor_adapter_binding_id"
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
        or not executor_envelope_id
    ):
        denial = "missing_adapter_attachment_lineage_identity"
        created = False
    elif lineage != expected_lineage:
        denial = "invalid_lineage"
        created = False
    else:
        denial = ""
        created = True

    attachment_id = (
        _stable_id(
            "runtime-executor-adapter-attachment",
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
            executor_adapter_binding_id,
        )
        if created
        else ""
    )

    return {
        "schema": RUNTIME_EXECUTOR_ADAPTER_ATTACHMENT_SCHEMA + ".request",
        "adapter_attachment_request_created": created,
        "executor_adapter_attachment_id": attachment_id,
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
        "executor_adapter_binding_id": executor_adapter_binding_id,
        "adapter_attachment_status": "rejected",
        "executor_adapter_attached": False,
        "executor_invoked": False,
        "execution_started": False,
        "lineage": attachment_lineage,
        "adapter_metadata": _mapping(binding.get("adapter_metadata")),
        "capability_snapshot": _mapping(
            binding.get("adapter_capability_metadata")
        ),
        "policy_metadata": {
            "adapter_attachment_policy": "record_only_adapter_attachment_metadata",
            "attached_means_executor_invoked": False,
            "attached_means_execution_started": False,
            "operator_visible": True,
            "dry_run_compatible": True,
            "reason": "adapter_attachment_metadata_only_no_executor_invocation",
        },
        "audit_fields": {
            "record_only": True,
            "source_executor_adapter_binding_id": executor_adapter_binding_id,
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
        "scheduler_advanced": False,
        "executor_imported": False,
        "executor_invoked": False,
        "execution_started": False,
    }


def evaluate_runtime_executor_adapter_attachment(
    attachment_request: Any,
    *,
    existing_attachments: Any = None,
) -> dict[str, Any]:
    request = _mapping(attachment_request)
    existing = [_mapping(item) for item in _list(existing_attachments)]

    if not request:
        denial = "missing_adapter_attachment_request"
        attached = False
    elif request.get("adapter_attachment_request_created") is not True:
        denial = (
            request.get("denial_reason")
            or "adapter_attachment_request_not_created"
        )
        attached = False
    elif any(
        item.get("executor_adapter_binding_id")
        == request.get("executor_adapter_binding_id")
        or item.get("executor_envelope_id") == request.get("executor_envelope_id")
        or item.get("executor_adapter_attachment_id")
        == request.get("executor_adapter_attachment_id")
        for item in existing
    ):
        denial = "duplicate_executor_adapter_attachment"
        attached = False
    else:
        denial = ""
        attached = True

    return {
        "schema": RUNTIME_EXECUTOR_ADAPTER_ATTACHMENT_SCHEMA,
        "executor_adapter_attached": attached,
        "executor_adapter_attachment_id": (
            request.get("executor_adapter_attachment_id") or ""
        ),
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
        "executor_adapter_binding_id": (
            request.get("executor_adapter_binding_id") or ""
        ),
        "adapter_attachment_status": "attached" if attached else "rejected",
        "executor_invoked": False,
        "execution_started": False,
        "lineage": _mapping(request.get("lineage")),
        "adapter_metadata": _mapping(request.get("adapter_metadata")),
        "capability_snapshot": _mapping(request.get("capability_snapshot")),
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
        "scheduler_advanced": False,
        "executor_imported": False,
        "executor_invoked": False,
        "execution_started": False,
    }


def attach_runtime_executor_adapter(
    executor_adapter_binding: Any,
    *,
    existing_attachments: Any = None,
) -> dict[str, Any]:
    attachment_request = build_runtime_executor_adapter_attachment_request(
        executor_adapter_binding
    )
    attachment = evaluate_runtime_executor_adapter_attachment(
        attachment_request,
        existing_attachments=existing_attachments,
    )
    attachments = [_mapping(item) for item in _list(existing_attachments)]
    if attachment["executor_adapter_attached"]:
        attachments.append(attachment)

    return {
        "schema": RUNTIME_EXECUTOR_ADAPTER_ATTACHMENT_SCHEMA + ".submit",
        "ok": attachment["executor_adapter_attached"],
        "adapter_attachment_request": attachment_request,
        "executor_adapter_attachment": attachment,
        "adapter_attachment_status": attachment["adapter_attachment_status"],
        "executor_adapter_attached": attachment["executor_adapter_attached"],
        "executor_invoked": False,
        "execution_started": False,
        "attachments": attachments,
        "attachment_count": len(attachments),
        "executor_adapter_attachment_id": (
            attachment["executor_adapter_attachment_id"]
        ),
        "goal_id": attachment["goal_id"],
        "work_package_id": attachment["work_package_id"],
        "runtime_session_id": attachment["runtime_session_id"],
        "session_id": attachment["session_id"],
        "queue_entry_id": attachment["queue_entry_id"],
        "queue_id": attachment["queue_id"],
        "worker_claim_id": attachment["worker_claim_id"],
        "worker_id": attachment["worker_id"],
        "cycle_binding_id": attachment["cycle_binding_id"],
        "cycle_id": attachment["cycle_id"],
        "execution_request_id": attachment["execution_request_id"],
        "tick_id": attachment["tick_id"],
        "decision_id": attachment["decision_id"],
        "proposal_id": attachment["proposal_id"],
        "authorization_id": attachment["authorization_id"],
        "commit_id": attachment["commit_id"],
        "execution_admission_id": attachment["execution_admission_id"],
        "execution_permit_id": attachment["execution_permit_id"],
        "executor_envelope_id": attachment["executor_envelope_id"],
        "executor_adapter_binding_id": attachment["executor_adapter_binding_id"],
        "adapter_metadata": attachment["adapter_metadata"],
        "capability_snapshot": attachment["capability_snapshot"],
        "policy_metadata": attachment["policy_metadata"],
        "audit_fields": attachment["audit_fields"],
        "denial_reason": attachment["denial_reason"],
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
        "scheduler_advanced": False,
        "executor_imported": False,
        "executor_invoked": False,
        "execution_started": False,
    }


def build_runtime_executor_adapter_attachment_state(
    attachments: Any,
) -> dict[str, Any]:
    records = [_mapping(item) for item in _list(attachments)]
    attached = [
        item
        for item in records
        if item.get("adapter_attachment_status") == "attached"
    ]
    return {
        "schema": RUNTIME_EXECUTOR_ADAPTER_ATTACHMENT_SCHEMA + ".state",
        "adapter_attachment_status": "attached" if attached else "rejected",
        "executor_adapter_attached": bool(attached),
        "executor_invoked": False,
        "execution_started": False,
        "attachment_count": len(records),
        "attached_count": len(attached),
        "attached_executor_adapter_binding_ids": [
            item.get("executor_adapter_binding_id") or "" for item in attached
        ],
        "attachments": records,
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
        "scheduler_advanced": False,
        "executor_imported": False,
        "executor_invoked": False,
        "execution_started": False,
    }


__all__ = [
    "RUNTIME_EXECUTOR_ADAPTER_ATTACHMENT_SCHEMA",
    "build_runtime_executor_adapter_attachment_request",
    "evaluate_runtime_executor_adapter_attachment",
    "attach_runtime_executor_adapter",
    "build_runtime_executor_adapter_attachment_state",
]
