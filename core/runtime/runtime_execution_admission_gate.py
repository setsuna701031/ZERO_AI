from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_EXECUTION_ADMISSION_GATE_SCHEMA = "zero.runtime.execution_admission_gate.v1"


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


def build_runtime_execution_admission_request(action_commit: Any) -> dict[str, Any]:
    commit = _mapping(action_commit)
    lineage = _mapping(commit.get("lineage"))
    goal_id = _text(commit.get("goal_id"))
    work_package_id = _text(commit.get("work_package_id"))
    runtime_session_id = _text(commit.get("runtime_session_id"))
    queue_entry_id = _text(commit.get("queue_entry_id"))
    worker_claim_id = _text(commit.get("worker_claim_id"))
    cycle_binding_id = _text(commit.get("cycle_binding_id"))
    execution_request_id = _text(commit.get("execution_request_id"))
    tick_id = _text(commit.get("tick_id"))
    decision_id = _text(commit.get("decision_id"))
    proposal_id = _text(commit.get("proposal_id"))
    authorization_id = _text(commit.get("authorization_id"))
    commit_id = _text(commit.get("commit_id"))

    lineage_valid = lineage == {
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
        "worker_claim_id": worker_claim_id,
        "cycle_binding_id": cycle_binding_id,
        "execution_request_id": execution_request_id,
        "tick_id": tick_id,
        "decision_id": decision_id,
        "proposal_id": proposal_id,
        "authorization_id": authorization_id,
    }

    if not commit:
        denial = "missing_action_commit"
        created = False
    elif commit.get("commit_admitted") is not True:
        denial = commit.get("denial_reason") or "action_commit_not_admitted"
        created = False
    elif commit.get("commit_status") != "committed":
        denial = "action_commit_not_committed"
        created = False
    elif not commit_id:
        denial = "missing_commit_id"
        created = False
    elif (
        not goal_id
        or not work_package_id
        or not runtime_session_id
        or not queue_entry_id
        or not worker_claim_id
        or not cycle_binding_id
        or not execution_request_id
        or not tick_id
        or not decision_id
        or not proposal_id
        or not authorization_id
    ):
        denial = "missing_execution_admission_lineage_identity"
        created = False
    elif not lineage_valid:
        denial = "invalid_lineage"
        created = False
    else:
        denial = ""
        created = True

    admission_id = (
        _stable_id(
            "runtime-execution-admission",
            goal_id,
            runtime_session_id,
            execution_request_id,
            tick_id,
            decision_id,
            proposal_id,
            authorization_id,
            commit_id,
        )
        if created
        else ""
    )
    admission_lineage = {
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
        "queue_id": queue_entry_id,
        "worker_claim_id": worker_claim_id,
        "worker_id": worker_claim_id,
        "cycle_binding_id": cycle_binding_id,
        "cycle_id": cycle_binding_id,
        "execution_request_id": execution_request_id,
        "tick_id": tick_id,
        "decision_id": decision_id,
        "proposal_id": proposal_id,
        "authorization_id": authorization_id,
        "commit_id": commit_id,
    }

    return {
        "schema": RUNTIME_EXECUTION_ADMISSION_GATE_SCHEMA + ".request",
        "execution_admission_request_created": created,
        "execution_admission_id": admission_id,
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
        "queue_id": queue_entry_id,
        "worker_claim_id": worker_claim_id,
        "worker_id": worker_claim_id,
        "cycle_binding_id": cycle_binding_id,
        "cycle_id": cycle_binding_id,
        "execution_request_id": execution_request_id,
        "tick_id": tick_id,
        "decision_id": decision_id,
        "proposal_id": proposal_id,
        "authorization_id": authorization_id,
        "commit_id": commit_id,
        "execution_admission_status": "denied",
        "execution_allowed": False,
        "lineage": admission_lineage,
        "policy_metadata": {
            "admission_policy": "record_only_execution_preparation",
            "may_prepare_execution": created,
            "execution_allowed": False,
        },
        "audit_fields": {
            "record_only": True,
            "source_commit_status": commit.get("commit_status") or "",
            "commit_means_execute": _mapping(commit.get("commit_metadata")).get(
                "commit_means_execute"
            )
            is True,
        },
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "filesystem_mutated": False,
        "code_mutated": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "runtime_executed": False,
        "progress_memory_written": False,
    }


def evaluate_runtime_execution_admission(
    admission_request: Any,
    *,
    existing_admissions: Any = None,
) -> dict[str, Any]:
    request = _mapping(admission_request)
    existing = [_mapping(item) for item in _list(existing_admissions)]

    if not request:
        denial = "missing_execution_admission_request"
        admitted = False
    elif request.get("execution_admission_request_created") is not True:
        denial = request.get("denial_reason") or "execution_admission_request_not_created"
        admitted = False
    elif any(
        item.get("commit_id") == request.get("commit_id")
        or item.get("authorization_id") == request.get("authorization_id")
        or item.get("execution_admission_id") == request.get("execution_admission_id")
        for item in existing
    ):
        denial = "duplicate_execution_admission"
        admitted = False
    else:
        denial = ""
        admitted = True

    return {
        "schema": RUNTIME_EXECUTION_ADMISSION_GATE_SCHEMA,
        "execution_admission_admitted": admitted,
        "execution_admission_id": request.get("execution_admission_id") or "",
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
        "execution_admission_status": "admitted" if admitted else "denied",
        "execution_allowed": False,
        "lineage": _mapping(request.get("lineage")),
        "policy_metadata": _mapping(request.get("policy_metadata")),
        "audit_fields": _mapping(request.get("audit_fields")),
        "denial_reason": denial,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "filesystem_mutated": False,
        "code_mutated": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "runtime_executed": False,
        "progress_memory_written": False,
    }


def admit_runtime_execution(
    action_commit: Any,
    *,
    existing_admissions: Any = None,
) -> dict[str, Any]:
    admission_request = build_runtime_execution_admission_request(action_commit)
    admission = evaluate_runtime_execution_admission(
        admission_request,
        existing_admissions=existing_admissions,
    )
    admissions = [_mapping(item) for item in _list(existing_admissions)]
    if admission["execution_admission_admitted"]:
        admissions.append(admission)

    return {
        "schema": RUNTIME_EXECUTION_ADMISSION_GATE_SCHEMA + ".submit",
        "ok": admission["execution_admission_admitted"],
        "execution_admission_request": admission_request,
        "execution_admission": admission,
        "execution_admission_status": admission["execution_admission_status"],
        "execution_allowed": False,
        "admissions": admissions,
        "admission_count": len(admissions),
        "execution_admission_id": admission["execution_admission_id"],
        "goal_id": admission["goal_id"],
        "work_package_id": admission["work_package_id"],
        "runtime_session_id": admission["runtime_session_id"],
        "session_id": admission["session_id"],
        "queue_entry_id": admission["queue_entry_id"],
        "queue_id": admission["queue_id"],
        "worker_claim_id": admission["worker_claim_id"],
        "worker_id": admission["worker_id"],
        "cycle_binding_id": admission["cycle_binding_id"],
        "cycle_id": admission["cycle_id"],
        "execution_request_id": admission["execution_request_id"],
        "tick_id": admission["tick_id"],
        "decision_id": admission["decision_id"],
        "proposal_id": admission["proposal_id"],
        "authorization_id": admission["authorization_id"],
        "commit_id": admission["commit_id"],
        "policy_metadata": admission["policy_metadata"],
        "audit_fields": admission["audit_fields"],
        "denial_reason": admission["denial_reason"],
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "filesystem_mutated": False,
        "code_mutated": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "runtime_executed": False,
        "progress_memory_written": False,
    }


def build_runtime_execution_admission_state(admissions: Any) -> dict[str, Any]:
    records = [_mapping(item) for item in _list(admissions)]
    admitted = [
        item
        for item in records
        if item.get("execution_admission_status") == "admitted"
    ]
    return {
        "schema": RUNTIME_EXECUTION_ADMISSION_GATE_SCHEMA + ".state",
        "execution_admission_status": "admitted" if admitted else "denied",
        "execution_allowed": False,
        "admission_count": len(records),
        "admitted_count": len(admitted),
        "admitted_commit_ids": [item.get("commit_id") or "" for item in admitted],
        "admissions": records,
        "runtime_state_mutated": False,
        "task_executed": False,
        "direct_dispatch_requested": False,
        "filesystem_mutated": False,
        "code_mutated": False,
        "cursor_mutated": False,
        "cursor_advanced": False,
        "runtime_executed": False,
        "progress_memory_written": False,
    }


__all__ = [
    "RUNTIME_EXECUTION_ADMISSION_GATE_SCHEMA",
    "build_runtime_execution_admission_request",
    "evaluate_runtime_execution_admission",
    "admit_runtime_execution",
    "build_runtime_execution_admission_state",
]
