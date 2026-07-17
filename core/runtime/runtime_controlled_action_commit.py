from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_CONTROLLED_ACTION_COMMIT_SCHEMA = "zero.runtime.controlled_action_commit.v1"


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


def build_controlled_action_commit_request(
    action_authorization: Any,
) -> dict[str, Any]:
    authorization = _mapping(action_authorization)
    lineage = _mapping(authorization.get("lineage"))
    goal_id = _text(authorization.get("goal_id"))
    work_package_id = _text(authorization.get("work_package_id"))
    runtime_session_id = _text(authorization.get("runtime_session_id"))
    queue_entry_id = _text(authorization.get("queue_entry_id"))
    worker_claim_id = _text(authorization.get("worker_claim_id"))
    cycle_binding_id = _text(authorization.get("cycle_binding_id"))
    execution_request_id = _text(authorization.get("execution_request_id"))
    tick_id = _text(authorization.get("tick_id"))
    decision_id = _text(authorization.get("decision_id"))
    proposal_id = _text(authorization.get("proposal_id"))
    authorization_id = _text(authorization.get("authorization_id"))

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
    }

    if not authorization:
        denial = "missing_action_authorization"
        created = False
    elif authorization.get("authorization_admitted") is not True:
        denial = authorization.get("denial_reason") or "action_authorization_not_admitted"
        created = False
    elif authorization.get("authorization_status") != "authorized":
        denial = "action_authorization_not_authorized"
        created = False
    elif not authorization_id:
        denial = "missing_authorization_id"
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
    ):
        denial = "missing_commit_lineage_identity"
        created = False
    elif not lineage_valid:
        denial = "invalid_lineage"
        created = False
    else:
        denial = ""
        created = True

    commit_id = (
        _stable_id(
            "runtime-controlled-action-commit",
            goal_id,
            runtime_session_id,
            execution_request_id,
            tick_id,
            decision_id,
            proposal_id,
            authorization_id,
        )
        if created
        else ""
    )
    commit_lineage = {
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

    return {
        "schema": RUNTIME_CONTROLLED_ACTION_COMMIT_SCHEMA + ".request",
        "commit_request_created": created,
        "commit_id": commit_id,
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
        "commit_status": "not_ready" if created else "rejected",
        "lineage": commit_lineage,
        "commit_metadata": {
            "selected": created,
            "frozen": created,
            "immutable": created,
            "commit_scope": "single_controlled_action",
            "commit_means_execute": False,
        },
        "audit_fields": {
            "record_only": True,
            "source_authorization_status": authorization.get("authorization_status") or "",
            "source_authorized_boolean": authorization.get("authorized") is True,
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


def evaluate_controlled_action_commit_admission(
    commit_request: Any,
    *,
    existing_commits: Any = None,
) -> dict[str, Any]:
    request = _mapping(commit_request)
    existing = [_mapping(item) for item in _list(existing_commits)]

    if not request:
        denial = "missing_commit_request"
        admitted = False
    elif request.get("commit_request_created") is not True:
        denial = request.get("denial_reason") or "commit_request_not_created"
        admitted = False
    elif any(
        item.get("authorization_id") == request.get("authorization_id")
        or item.get("proposal_id") == request.get("proposal_id")
        or item.get("commit_id") == request.get("commit_id")
        for item in existing
    ):
        denial = "duplicate_action_commit"
        admitted = False
    else:
        denial = ""
        admitted = True

    return {
        "schema": RUNTIME_CONTROLLED_ACTION_COMMIT_SCHEMA,
        "commit_admitted": admitted,
        "commit_id": request.get("commit_id") or "",
        "goal_id": request.get("goal_id") or "",
        "work_package_id": request.get("work_package_id") or "",
        "runtime_session_id": request.get("runtime_session_id") or "",
        "session_id": request.get("runtime_session_id") or "",
        "queue_entry_id": request.get("queue_entry_id") or "",
        "queue_id": request.get("queue_entry_id") or "",
        "worker_claim_id": request.get("worker_claim_id") or "",
        "worker_id": request.get("worker_claim_id") or "",
        "cycle_binding_id": request.get("cycle_binding_id") or "",
        "cycle_id": request.get("cycle_binding_id") or "",
        "execution_request_id": request.get("execution_request_id") or "",
        "tick_id": request.get("tick_id") or "",
        "decision_id": request.get("decision_id") or "",
        "proposal_id": request.get("proposal_id") or "",
        "authorization_id": request.get("authorization_id") or "",
        "commit_status": "committed" if admitted else "rejected",
        "lineage": _mapping(request.get("lineage")),
        "commit_metadata": _mapping(request.get("commit_metadata")),
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


def commit_controlled_action(
    action_authorization: Any,
    *,
    existing_commits: Any = None,
) -> dict[str, Any]:
    commit_request = build_controlled_action_commit_request(action_authorization)
    commit = evaluate_controlled_action_commit_admission(
        commit_request,
        existing_commits=existing_commits,
    )
    commits = [_mapping(item) for item in _list(existing_commits)]
    if commit["commit_admitted"]:
        commits.append(commit)

    return {
        "schema": RUNTIME_CONTROLLED_ACTION_COMMIT_SCHEMA + ".submit",
        "ok": commit["commit_admitted"],
        "commit_request": commit_request,
        "action_commit": commit,
        "commit_status": commit["commit_status"],
        "committed": commit["commit_admitted"],
        "commits": commits,
        "commit_count": len(commits),
        "commit_id": commit["commit_id"],
        "goal_id": commit["goal_id"],
        "work_package_id": commit["work_package_id"],
        "runtime_session_id": commit["runtime_session_id"],
        "session_id": commit["session_id"],
        "queue_entry_id": commit["queue_entry_id"],
        "queue_id": commit["queue_id"],
        "worker_claim_id": commit["worker_claim_id"],
        "worker_id": commit["worker_id"],
        "cycle_binding_id": commit["cycle_binding_id"],
        "cycle_id": commit["cycle_id"],
        "execution_request_id": commit["execution_request_id"],
        "tick_id": commit["tick_id"],
        "decision_id": commit["decision_id"],
        "proposal_id": commit["proposal_id"],
        "authorization_id": commit["authorization_id"],
        "commit_metadata": commit["commit_metadata"],
        "audit_fields": commit["audit_fields"],
        "denial_reason": commit["denial_reason"],
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


def build_controlled_action_commit_state(commits: Any) -> dict[str, Any]:
    records = [_mapping(item) for item in _list(commits)]
    committed = [item for item in records if item.get("commit_status") == "committed"]
    return {
        "schema": RUNTIME_CONTROLLED_ACTION_COMMIT_SCHEMA + ".state",
        "commit_status": "committed" if committed else "not_ready",
        "committed_count": len(committed),
        "commit_count": len(records),
        "committed_authorization_ids": [
            item.get("authorization_id") or "" for item in committed
        ],
        "committed_proposal_ids": [item.get("proposal_id") or "" for item in committed],
        "commits": records,
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
    "RUNTIME_CONTROLLED_ACTION_COMMIT_SCHEMA",
    "build_controlled_action_commit_request",
    "evaluate_controlled_action_commit_admission",
    "commit_controlled_action",
    "build_controlled_action_commit_state",
]
