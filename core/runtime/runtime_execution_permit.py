from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_EXECUTION_PERMIT_SCHEMA = "zero.runtime.execution_permit.v1"


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


def build_runtime_execution_permit_request(
    execution_admission: Any,
) -> dict[str, Any]:
    admission = _mapping(execution_admission)
    lineage = _mapping(admission.get("lineage"))
    goal_id = _text(admission.get("goal_id"))
    work_package_id = _text(admission.get("work_package_id"))
    runtime_session_id = _text(admission.get("runtime_session_id"))
    session_id = _text(admission.get("session_id")) or runtime_session_id
    queue_entry_id = _text(admission.get("queue_entry_id"))
    queue_id = _text(admission.get("queue_id")) or queue_entry_id
    worker_claim_id = _text(admission.get("worker_claim_id"))
    worker_id = _text(admission.get("worker_id")) or worker_claim_id
    cycle_binding_id = _text(admission.get("cycle_binding_id"))
    cycle_id = _text(admission.get("cycle_id")) or cycle_binding_id
    execution_request_id = _text(admission.get("execution_request_id"))
    tick_id = _text(admission.get("tick_id"))
    decision_id = _text(admission.get("decision_id"))
    proposal_id = _text(admission.get("proposal_id"))
    authorization_id = _text(admission.get("authorization_id"))
    commit_id = _text(admission.get("commit_id"))
    execution_admission_id = _text(admission.get("execution_admission_id"))

    permit_lineage = {
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
    }

    if not admission:
        denial = "missing_execution_admission"
        created = False
    elif admission.get("execution_admission_admitted") is not True:
        denial = admission.get("denial_reason") or "execution_admission_not_admitted"
        created = False
    elif admission.get("execution_admission_status") != "admitted":
        denial = "execution_admission_not_admitted"
        created = False
    elif not execution_admission_id:
        denial = "missing_execution_admission_id"
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
    ):
        denial = "missing_execution_permit_lineage_identity"
        created = False
    elif lineage != expected_lineage:
        denial = "invalid_lineage"
        created = False
    else:
        denial = ""
        created = True

    permit_id = (
        _stable_id(
            "runtime-execution-permit",
            goal_id,
            runtime_session_id,
            execution_request_id,
            tick_id,
            decision_id,
            proposal_id,
            authorization_id,
            commit_id,
            execution_admission_id,
        )
        if created
        else ""
    )

    return {
        "schema": RUNTIME_EXECUTION_PERMIT_SCHEMA + ".request",
        "execution_permit_request_created": created,
        "execution_permit_id": permit_id,
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
        "permit_status": "permit_denied",
        "execution_permitted": False,
        "lineage": permit_lineage,
        "policy_metadata": {
            "permit_policy": "record_only_final_execution_safety_gate",
            "permit_granted_means_execute": False,
            "execution_permitted": False,
            "dry_run_compatible": True,
            "reason": "permit_metadata_only_no_execution_surface",
        },
        "audit_fields": {
            "record_only": True,
            "source_execution_admission_status": (
                admission.get("execution_admission_status") or ""
            ),
            "source_execution_allowed": admission.get("execution_allowed") is True,
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
        "scheduler_dispatched": False,
        "executor_called": False,
    }


def evaluate_runtime_execution_permit(
    permit_request: Any,
    *,
    existing_permits: Any = None,
) -> dict[str, Any]:
    request = _mapping(permit_request)
    existing = [_mapping(item) for item in _list(existing_permits)]

    if not request:
        denial = "missing_execution_permit_request"
        granted = False
    elif request.get("execution_permit_request_created") is not True:
        denial = request.get("denial_reason") or "execution_permit_request_not_created"
        granted = False
    elif any(
        item.get("execution_admission_id") == request.get("execution_admission_id")
        or item.get("commit_id") == request.get("commit_id")
        or item.get("execution_permit_id") == request.get("execution_permit_id")
        for item in existing
    ):
        denial = "duplicate_execution_permit"
        granted = False
    else:
        denial = ""
        granted = True

    return {
        "schema": RUNTIME_EXECUTION_PERMIT_SCHEMA,
        "execution_permit_granted": granted,
        "execution_permit_id": request.get("execution_permit_id") or "",
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
        "permit_status": "permit_granted" if granted else "permit_denied",
        "execution_permitted": False,
        "lineage": _mapping(request.get("lineage")),
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
        "scheduler_dispatched": False,
        "executor_called": False,
    }


def permit_runtime_execution(
    execution_admission: Any,
    *,
    existing_permits: Any = None,
) -> dict[str, Any]:
    permit_request = build_runtime_execution_permit_request(execution_admission)
    permit = evaluate_runtime_execution_permit(
        permit_request,
        existing_permits=existing_permits,
    )
    permits = [_mapping(item) for item in _list(existing_permits)]
    if permit["execution_permit_granted"]:
        permits.append(permit)

    return {
        "schema": RUNTIME_EXECUTION_PERMIT_SCHEMA + ".submit",
        "ok": permit["execution_permit_granted"],
        "execution_permit_request": permit_request,
        "execution_permit": permit,
        "permit_status": permit["permit_status"],
        "execution_permitted": False,
        "permits": permits,
        "permit_count": len(permits),
        "execution_permit_id": permit["execution_permit_id"],
        "goal_id": permit["goal_id"],
        "work_package_id": permit["work_package_id"],
        "runtime_session_id": permit["runtime_session_id"],
        "session_id": permit["session_id"],
        "queue_entry_id": permit["queue_entry_id"],
        "queue_id": permit["queue_id"],
        "worker_claim_id": permit["worker_claim_id"],
        "worker_id": permit["worker_id"],
        "cycle_binding_id": permit["cycle_binding_id"],
        "cycle_id": permit["cycle_id"],
        "execution_request_id": permit["execution_request_id"],
        "tick_id": permit["tick_id"],
        "decision_id": permit["decision_id"],
        "proposal_id": permit["proposal_id"],
        "authorization_id": permit["authorization_id"],
        "commit_id": permit["commit_id"],
        "execution_admission_id": permit["execution_admission_id"],
        "policy_metadata": permit["policy_metadata"],
        "audit_fields": permit["audit_fields"],
        "denial_reason": permit["denial_reason"],
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
        "scheduler_dispatched": False,
        "executor_called": False,
    }


def build_runtime_execution_permit_state(permits: Any) -> dict[str, Any]:
    records = [_mapping(item) for item in _list(permits)]
    granted = [
        item for item in records if item.get("permit_status") == "permit_granted"
    ]
    return {
        "schema": RUNTIME_EXECUTION_PERMIT_SCHEMA + ".state",
        "permit_status": "permit_granted" if granted else "permit_denied",
        "execution_permitted": False,
        "permit_count": len(records),
        "granted_count": len(granted),
        "granted_execution_admission_ids": [
            item.get("execution_admission_id") or "" for item in granted
        ],
        "permits": records,
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
        "scheduler_dispatched": False,
        "executor_called": False,
    }


__all__ = [
    "RUNTIME_EXECUTION_PERMIT_SCHEMA",
    "build_runtime_execution_permit_request",
    "evaluate_runtime_execution_permit",
    "permit_runtime_execution",
    "build_runtime_execution_permit_state",
]
