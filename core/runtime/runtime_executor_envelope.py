from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_EXECUTOR_ENVELOPE_SCHEMA = "zero.runtime.executor_envelope.v1"


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


def build_runtime_executor_envelope_request(
    execution_permit: Any,
) -> dict[str, Any]:
    permit = _mapping(execution_permit)
    lineage = _mapping(permit.get("lineage"))
    goal_id = _text(permit.get("goal_id"))
    work_package_id = _text(permit.get("work_package_id"))
    runtime_session_id = _text(permit.get("runtime_session_id"))
    session_id = _text(permit.get("session_id")) or runtime_session_id
    queue_entry_id = _text(permit.get("queue_entry_id"))
    queue_id = _text(permit.get("queue_id")) or queue_entry_id
    worker_claim_id = _text(permit.get("worker_claim_id"))
    worker_id = _text(permit.get("worker_id")) or worker_claim_id
    cycle_binding_id = _text(permit.get("cycle_binding_id"))
    cycle_id = _text(permit.get("cycle_id")) or cycle_binding_id
    execution_request_id = _text(permit.get("execution_request_id"))
    tick_id = _text(permit.get("tick_id"))
    decision_id = _text(permit.get("decision_id"))
    proposal_id = _text(permit.get("proposal_id"))
    authorization_id = _text(permit.get("authorization_id"))
    commit_id = _text(permit.get("commit_id"))
    execution_admission_id = _text(permit.get("execution_admission_id"))
    execution_permit_id = _text(permit.get("execution_permit_id"))

    envelope_lineage = {
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
    }

    if not permit:
        denial = "missing_execution_permit"
        created = False
    elif permit.get("execution_permit_granted") is not True:
        denial = permit.get("denial_reason") or "execution_permit_not_granted"
        created = False
    elif permit.get("permit_status") != "permit_granted":
        denial = "execution_permit_not_granted"
        created = False
    elif not execution_permit_id:
        denial = "missing_execution_permit_id"
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
    ):
        denial = "missing_executor_envelope_lineage_identity"
        created = False
    elif lineage != expected_lineage:
        denial = "invalid_lineage"
        created = False
    else:
        denial = ""
        created = True

    envelope_id = (
        _stable_id(
            "runtime-executor-envelope",
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
        )
        if created
        else ""
    )

    return {
        "schema": RUNTIME_EXECUTOR_ENVELOPE_SCHEMA + ".request",
        "executor_envelope_request_created": created,
        "executor_envelope_id": envelope_id,
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
        "executor_envelope_status": "rejected",
        "execution_started": False,
        "executor_attached": False,
        "lineage": envelope_lineage,
        "execution_metadata_snapshot": {
            "source_permit_status": permit.get("permit_status") or "",
            "source_execution_permitted": permit.get("execution_permitted") is True,
            "dry_run_container": True,
            "isolated_boundary_prepared": created,
        },
        "safety_flags": {
            "record_only": True,
            "execution_started": False,
            "executor_attached": False,
            "filesystem_mutated": False,
            "repo_mutated": False,
            "progress_updated": False,
            "cursor_moved": False,
        },
        "policy_metadata": {
            "envelope_policy": "record_only_isolated_executor_boundary",
            "prepared_means_execute": False,
            "operator_visible": True,
            "dry_run_compatible": True,
            "reason": "executor_envelope_metadata_only_no_execution_start",
        },
        "audit_fields": {
            "record_only": True,
            "source_execution_permit_id": execution_permit_id,
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
        "cursor_moved": False,
        "runtime_executed": False,
        "progress_memory_written": False,
        "progress_updated": False,
        "scheduler_called": False,
        "executor_invoked": False,
    }


def evaluate_runtime_executor_envelope(
    envelope_request: Any,
    *,
    existing_envelopes: Any = None,
) -> dict[str, Any]:
    request = _mapping(envelope_request)
    existing = [_mapping(item) for item in _list(existing_envelopes)]

    if not request:
        denial = "missing_executor_envelope_request"
        prepared = False
    elif request.get("executor_envelope_request_created") is not True:
        denial = request.get("denial_reason") or "executor_envelope_request_not_created"
        prepared = False
    elif any(
        item.get("execution_permit_id") == request.get("execution_permit_id")
        or item.get("execution_admission_id") == request.get("execution_admission_id")
        or item.get("commit_id") == request.get("commit_id")
        or item.get("executor_envelope_id") == request.get("executor_envelope_id")
        for item in existing
    ):
        denial = "duplicate_executor_envelope"
        prepared = False
    else:
        denial = ""
        prepared = True

    return {
        "schema": RUNTIME_EXECUTOR_ENVELOPE_SCHEMA,
        "executor_envelope_prepared": prepared,
        "executor_envelope_id": request.get("executor_envelope_id") or "",
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
        "executor_envelope_status": "prepared" if prepared else "rejected",
        "execution_started": False,
        "executor_attached": False,
        "lineage": _mapping(request.get("lineage")),
        "execution_metadata_snapshot": _mapping(
            request.get("execution_metadata_snapshot")
        ),
        "safety_flags": _mapping(request.get("safety_flags")),
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
        "cursor_moved": False,
        "runtime_executed": False,
        "progress_memory_written": False,
        "progress_updated": False,
        "scheduler_called": False,
        "executor_invoked": False,
    }


def prepare_runtime_executor_envelope(
    execution_permit: Any,
    *,
    existing_envelopes: Any = None,
) -> dict[str, Any]:
    envelope_request = build_runtime_executor_envelope_request(execution_permit)
    envelope = evaluate_runtime_executor_envelope(
        envelope_request,
        existing_envelopes=existing_envelopes,
    )
    envelopes = [_mapping(item) for item in _list(existing_envelopes)]
    if envelope["executor_envelope_prepared"]:
        envelopes.append(envelope)

    return {
        "schema": RUNTIME_EXECUTOR_ENVELOPE_SCHEMA + ".submit",
        "ok": envelope["executor_envelope_prepared"],
        "executor_envelope_request": envelope_request,
        "executor_envelope": envelope,
        "executor_envelope_status": envelope["executor_envelope_status"],
        "execution_started": False,
        "executor_attached": False,
        "envelopes": envelopes,
        "envelope_count": len(envelopes),
        "executor_envelope_id": envelope["executor_envelope_id"],
        "goal_id": envelope["goal_id"],
        "work_package_id": envelope["work_package_id"],
        "runtime_session_id": envelope["runtime_session_id"],
        "session_id": envelope["session_id"],
        "queue_entry_id": envelope["queue_entry_id"],
        "queue_id": envelope["queue_id"],
        "worker_claim_id": envelope["worker_claim_id"],
        "worker_id": envelope["worker_id"],
        "cycle_binding_id": envelope["cycle_binding_id"],
        "cycle_id": envelope["cycle_id"],
        "execution_request_id": envelope["execution_request_id"],
        "tick_id": envelope["tick_id"],
        "decision_id": envelope["decision_id"],
        "proposal_id": envelope["proposal_id"],
        "authorization_id": envelope["authorization_id"],
        "commit_id": envelope["commit_id"],
        "execution_admission_id": envelope["execution_admission_id"],
        "execution_permit_id": envelope["execution_permit_id"],
        "execution_metadata_snapshot": envelope["execution_metadata_snapshot"],
        "safety_flags": envelope["safety_flags"],
        "policy_metadata": envelope["policy_metadata"],
        "audit_fields": envelope["audit_fields"],
        "denial_reason": envelope["denial_reason"],
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "filesystem_mutated": False,
        "code_mutated": False,
        "repo_mutated": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "cursor_moved": False,
        "runtime_executed": False,
        "progress_memory_written": False,
        "progress_updated": False,
        "scheduler_called": False,
        "executor_invoked": False,
    }


def build_runtime_executor_envelope_state(envelopes: Any) -> dict[str, Any]:
    records = [_mapping(item) for item in _list(envelopes)]
    prepared = [
        item
        for item in records
        if item.get("executor_envelope_status") == "prepared"
    ]
    return {
        "schema": RUNTIME_EXECUTOR_ENVELOPE_SCHEMA + ".state",
        "executor_envelope_status": "prepared" if prepared else "rejected",
        "execution_started": False,
        "executor_attached": False,
        "envelope_count": len(records),
        "prepared_count": len(prepared),
        "prepared_execution_permit_ids": [
            item.get("execution_permit_id") or "" for item in prepared
        ],
        "envelopes": records,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "filesystem_mutated": False,
        "code_mutated": False,
        "repo_mutated": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "cursor_moved": False,
        "runtime_executed": False,
        "progress_memory_written": False,
        "progress_updated": False,
        "scheduler_called": False,
        "executor_invoked": False,
    }


__all__ = [
    "RUNTIME_EXECUTOR_ENVELOPE_SCHEMA",
    "build_runtime_executor_envelope_request",
    "evaluate_runtime_executor_envelope",
    "prepare_runtime_executor_envelope",
    "build_runtime_executor_envelope_state",
]
