from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping


RUNTIME_CONTROLLED_ACTION_PROPOSAL_SCHEMA = (
    "zero.runtime.controlled_action_proposal.v1"
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


def build_controlled_action_proposal_request(
    controlled_tick_decision: Any,
) -> dict[str, Any]:
    decision = _mapping(controlled_tick_decision)
    lineage = _mapping(decision.get("lineage"))
    goal_id = _text(decision.get("goal_id"))
    work_package_id = _text(decision.get("work_package_id"))
    runtime_session_id = _text(decision.get("runtime_session_id"))
    queue_entry_id = _text(decision.get("queue_entry_id"))
    worker_claim_id = _text(decision.get("worker_claim_id"))
    cycle_binding_id = _text(decision.get("cycle_binding_id"))
    execution_request_id = _text(decision.get("execution_request_id"))
    tick_id = _text(decision.get("tick_id"))
    decision_id = _text(decision.get("decision_id"))

    lineage_valid = lineage == {
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
        "worker_claim_id": worker_claim_id,
        "cycle_binding_id": cycle_binding_id,
        "execution_request_id": execution_request_id,
        "tick_id": tick_id,
    }

    if not decision:
        denial = "missing_controlled_tick_decision"
        created = False
    elif decision.get("decision_admitted") is not True:
        denial = decision.get("denial_reason") or "controlled_tick_decision_not_admitted"
        created = False
    elif decision.get("decision_status") != "decision_ready":
        denial = "controlled_tick_decision_not_ready"
        created = False
    elif not decision_id:
        denial = "missing_decision_id"
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
    ):
        denial = "missing_proposal_lineage_identity"
        created = False
    elif not lineage_valid:
        denial = "invalid_lineage"
        created = False
    else:
        denial = ""
        created = True

    proposal_id = (
        _stable_id(
            "runtime-controlled-action-proposal",
            goal_id,
            runtime_session_id,
            execution_request_id,
            tick_id,
            decision_id,
        )
        if created
        else ""
    )
    proposal_lineage = {
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

    return {
        "schema": RUNTIME_CONTROLLED_ACTION_PROPOSAL_SCHEMA + ".request",
        "proposal_request_created": created,
        "proposal_id": proposal_id,
        "goal_id": goal_id,
        "work_package_id": work_package_id,
        "runtime_session_id": runtime_session_id,
        "queue_entry_id": queue_entry_id,
        "worker_claim_id": worker_claim_id,
        "cycle_binding_id": cycle_binding_id,
        "execution_request_id": execution_request_id,
        "tick_id": tick_id,
        "decision_id": decision_id,
        "proposal_status": "not_ready" if created else "rejected",
        "lineage": proposal_lineage,
        "reason": "controlled_decision_ready_for_action_proposal" if created else denial,
        "state_metadata": {
            "decision_status": decision.get("decision_status") or "",
            "decision_reason": decision.get("reason") or "",
            "record_only": True,
        },
        "action_metadata": {
            "action_kind": "controlled_runtime_action_proposal",
            "proposal_scope": "single_tick",
            "execution_permitted": False,
            "mutation_permitted": False,
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


def evaluate_controlled_action_proposal_admission(
    proposal_request: Any,
    *,
    existing_proposals: Any = None,
) -> dict[str, Any]:
    request = _mapping(proposal_request)
    existing = [_mapping(item) for item in _list(existing_proposals)]

    if not request:
        denial = "missing_proposal_request"
        admitted = False
    elif request.get("proposal_request_created") is not True:
        denial = request.get("denial_reason") or "proposal_request_not_created"
        admitted = False
    elif any(
        item.get("decision_id") == request.get("decision_id")
        or item.get("tick_id") == request.get("tick_id")
        or item.get("proposal_id") == request.get("proposal_id")
        for item in existing
    ):
        denial = "duplicate_action_proposal"
        admitted = False
    else:
        denial = ""
        admitted = True

    return {
        "schema": RUNTIME_CONTROLLED_ACTION_PROPOSAL_SCHEMA,
        "proposal_admitted": admitted,
        "proposal_id": request.get("proposal_id") or "",
        "goal_id": request.get("goal_id") or "",
        "work_package_id": request.get("work_package_id") or "",
        "runtime_session_id": request.get("runtime_session_id") or "",
        "queue_entry_id": request.get("queue_entry_id") or "",
        "worker_claim_id": request.get("worker_claim_id") or "",
        "cycle_binding_id": request.get("cycle_binding_id") or "",
        "execution_request_id": request.get("execution_request_id") or "",
        "tick_id": request.get("tick_id") or "",
        "decision_id": request.get("decision_id") or "",
        "proposal_status": "action_proposed" if admitted else "rejected",
        "lineage": _mapping(request.get("lineage")),
        "reason": "controlled_action_proposal_ready" if admitted else denial,
        "state_metadata": _mapping(request.get("state_metadata")),
        "action_metadata": _mapping(request.get("action_metadata")),
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


def propose_controlled_action(
    controlled_tick_decision: Any,
    *,
    existing_proposals: Any = None,
) -> dict[str, Any]:
    proposal_request = build_controlled_action_proposal_request(
        controlled_tick_decision
    )
    proposal = evaluate_controlled_action_proposal_admission(
        proposal_request,
        existing_proposals=existing_proposals,
    )
    proposals = [_mapping(item) for item in _list(existing_proposals)]
    if proposal["proposal_admitted"]:
        proposals.append(proposal)

    return {
        "schema": RUNTIME_CONTROLLED_ACTION_PROPOSAL_SCHEMA + ".submit",
        "ok": proposal["proposal_admitted"],
        "proposal_request": proposal_request,
        "action_proposal": proposal,
        "proposal_status": proposal["proposal_status"],
        "action_proposed": proposal["proposal_admitted"],
        "proposals": proposals,
        "proposal_count": len(proposals),
        "proposal_id": proposal["proposal_id"],
        "goal_id": proposal["goal_id"],
        "work_package_id": proposal["work_package_id"],
        "runtime_session_id": proposal["runtime_session_id"],
        "queue_entry_id": proposal["queue_entry_id"],
        "worker_claim_id": proposal["worker_claim_id"],
        "cycle_binding_id": proposal["cycle_binding_id"],
        "execution_request_id": proposal["execution_request_id"],
        "tick_id": proposal["tick_id"],
        "decision_id": proposal["decision_id"],
        "reason": proposal["reason"],
        "state_metadata": proposal["state_metadata"],
        "action_metadata": proposal["action_metadata"],
        "denial_reason": proposal["denial_reason"],
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


def build_controlled_action_proposal_state(proposals: Any) -> dict[str, Any]:
    records = [_mapping(item) for item in _list(proposals)]
    proposed = [item for item in records if item.get("proposal_status") == "action_proposed"]
    return {
        "schema": RUNTIME_CONTROLLED_ACTION_PROPOSAL_SCHEMA + ".state",
        "proposal_status": "action_proposed" if proposed else "not_ready",
        "proposed_count": len(proposed),
        "proposal_count": len(records),
        "proposed_decision_ids": [
            item.get("decision_id") or "" for item in proposed
        ],
        "proposed_tick_ids": [item.get("tick_id") or "" for item in proposed],
        "proposals": records,
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
    "RUNTIME_CONTROLLED_ACTION_PROPOSAL_SCHEMA",
    "build_controlled_action_proposal_request",
    "evaluate_controlled_action_proposal_admission",
    "propose_controlled_action",
    "build_controlled_action_proposal_state",
]
