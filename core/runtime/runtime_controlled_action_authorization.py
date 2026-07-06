from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_CONTROLLED_ACTION_AUTHORIZATION_SCHEMA = (
    "zero.runtime.controlled_action_authorization.v1"
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


def build_controlled_action_authorization_request(
    action_proposal: Any,
) -> dict[str, Any]:
    proposal = _mapping(action_proposal)
    lineage = _mapping(proposal.get("lineage"))
    goal_id = _text(proposal.get("goal_id"))
    work_package_id = _text(proposal.get("work_package_id"))
    runtime_session_id = _text(proposal.get("runtime_session_id"))
    queue_entry_id = _text(proposal.get("queue_entry_id"))
    worker_claim_id = _text(proposal.get("worker_claim_id"))
    cycle_binding_id = _text(proposal.get("cycle_binding_id"))
    execution_request_id = _text(proposal.get("execution_request_id"))
    tick_id = _text(proposal.get("tick_id"))
    decision_id = _text(proposal.get("decision_id"))
    proposal_id = _text(proposal.get("proposal_id"))

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
    }

    if not proposal:
        denial = "missing_action_proposal"
        created = False
    elif proposal.get("proposal_admitted") is not True:
        denial = proposal.get("denial_reason") or "action_proposal_not_admitted"
        created = False
    elif proposal.get("proposal_status") != "action_proposed":
        denial = "action_proposal_not_proposed"
        created = False
    elif not proposal_id:
        denial = "missing_proposal_id"
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
    ):
        denial = "missing_authorization_lineage_identity"
        created = False
    elif not lineage_valid:
        denial = "invalid_lineage"
        created = False
    else:
        denial = ""
        created = True

    authorization_id = (
        _stable_id(
            "runtime-controlled-action-authorization",
            goal_id,
            runtime_session_id,
            execution_request_id,
            tick_id,
            decision_id,
            proposal_id,
        )
        if created
        else ""
    )
    authorization_lineage = {
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
    }

    return {
        "schema": RUNTIME_CONTROLLED_ACTION_AUTHORIZATION_SCHEMA + ".request",
        "authorization_request_created": created,
        "authorization_id": authorization_id,
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
        "authorization_status": "denied",
        "authorized": False,
        "lineage": authorization_lineage,
        "policy_reason": (
            "authorization_metadata_created_pending_operator_approval"
            if created
            else denial
        ),
        "approval_metadata": {
            "operator_approval_required": True,
            "operator_approved": False,
            "approval_source": "",
        },
        "safety_flags": {
            "record_only": True,
            "execution_permitted": False,
            "mutation_permitted": False,
            "filesystem_write_permitted": False,
            "cursor_movement_permitted": False,
            "progress_update_permitted": False,
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


def evaluate_controlled_action_authorization_admission(
    authorization_request: Any,
    *,
    existing_authorizations: Any = None,
) -> dict[str, Any]:
    request = _mapping(authorization_request)
    existing = [_mapping(item) for item in _list(existing_authorizations)]

    if not request:
        denial = "missing_authorization_request"
        admitted = False
    elif request.get("authorization_request_created") is not True:
        denial = request.get("denial_reason") or "authorization_request_not_created"
        admitted = False
    elif any(
        item.get("proposal_id") == request.get("proposal_id")
        or item.get("decision_id") == request.get("decision_id")
        or item.get("authorization_id") == request.get("authorization_id")
        for item in existing
    ):
        denial = "duplicate_action_authorization"
        admitted = False
    else:
        denial = ""
        admitted = True

    return {
        "schema": RUNTIME_CONTROLLED_ACTION_AUTHORIZATION_SCHEMA,
        "authorization_admitted": admitted,
        "authorization_id": request.get("authorization_id") or "",
        "goal_id": request.get("goal_id") or "",
        "work_package_id": request.get("work_package_id") or "",
        "runtime_session_id": request.get("runtime_session_id") or "",
        "queue_entry_id": request.get("queue_entry_id") or "",
        "worker_claim_id": request.get("worker_claim_id") or "",
        "cycle_binding_id": request.get("cycle_binding_id") or "",
        "execution_request_id": request.get("execution_request_id") or "",
        "tick_id": request.get("tick_id") or "",
        "decision_id": request.get("decision_id") or "",
        "proposal_id": request.get("proposal_id") or "",
        "authorization_status": "authorized" if admitted else "denied",
        "authorized": False,
        "lineage": _mapping(request.get("lineage")),
        "policy_reason": (
            "metadata_authorized_but_execution_not_permitted"
            if admitted
            else denial
        ),
        "approval_metadata": _mapping(request.get("approval_metadata")),
        "safety_flags": _mapping(request.get("safety_flags")),
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


def authorize_controlled_action(
    action_proposal: Any,
    *,
    existing_authorizations: Any = None,
) -> dict[str, Any]:
    authorization_request = build_controlled_action_authorization_request(
        action_proposal
    )
    authorization = evaluate_controlled_action_authorization_admission(
        authorization_request,
        existing_authorizations=existing_authorizations,
    )
    authorizations = [_mapping(item) for item in _list(existing_authorizations)]
    if authorization["authorization_admitted"]:
        authorizations.append(authorization)

    return {
        "schema": RUNTIME_CONTROLLED_ACTION_AUTHORIZATION_SCHEMA + ".submit",
        "ok": authorization["authorization_admitted"],
        "authorization_request": authorization_request,
        "action_authorization": authorization,
        "authorization_status": authorization["authorization_status"],
        "authorized": False,
        "authorizations": authorizations,
        "authorization_count": len(authorizations),
        "authorization_id": authorization["authorization_id"],
        "goal_id": authorization["goal_id"],
        "work_package_id": authorization["work_package_id"],
        "runtime_session_id": authorization["runtime_session_id"],
        "queue_entry_id": authorization["queue_entry_id"],
        "worker_claim_id": authorization["worker_claim_id"],
        "cycle_binding_id": authorization["cycle_binding_id"],
        "execution_request_id": authorization["execution_request_id"],
        "tick_id": authorization["tick_id"],
        "decision_id": authorization["decision_id"],
        "proposal_id": authorization["proposal_id"],
        "policy_reason": authorization["policy_reason"],
        "approval_metadata": authorization["approval_metadata"],
        "safety_flags": authorization["safety_flags"],
        "denial_reason": authorization["denial_reason"],
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


def build_controlled_action_authorization_state(
    authorizations: Any,
) -> dict[str, Any]:
    records = [_mapping(item) for item in _list(authorizations)]
    admitted = [
        item for item in records if item.get("authorization_status") == "authorized"
    ]
    return {
        "schema": RUNTIME_CONTROLLED_ACTION_AUTHORIZATION_SCHEMA + ".state",
        "authorization_status": "authorized" if admitted else "denied",
        "authorized": False,
        "authorization_count": len(records),
        "authorized_metadata_count": len(admitted),
        "authorized_proposal_ids": [
            item.get("proposal_id") or "" for item in admitted
        ],
        "authorizations": records,
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
    "RUNTIME_CONTROLLED_ACTION_AUTHORIZATION_SCHEMA",
    "build_controlled_action_authorization_request",
    "evaluate_controlled_action_authorization_admission",
    "authorize_controlled_action",
    "build_controlled_action_authorization_state",
]
