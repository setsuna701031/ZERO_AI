from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional

from core.tasks.runtime_audit_artifact import build_runtime_audit_artifact
from core.tasks.runtime_audit_registry import RuntimeAuditRegistry
from core.tasks.runtime_replay_snapshot import build_runtime_replay_snapshot
from core.tasks.runtime_state_hygiene import clone_runtime_export, freeze_runtime_export, make_json_safe


RUNTIME_REPAIR_TRANSACTION_TYPE = "runtime_repair_transaction"
RUNTIME_REPAIR_TRANSACTION_VERSION = "runtime_repair_transaction.v1"

OPEN_TRANSACTION_STATES = {
    "created",
    "staged",
}

TERMINAL_TRANSACTION_STATES = {
    "committed",
    "rolled_back",
    "blocked",
    "failed",
}


def create_runtime_repair_transaction(
    *,
    task_id: Any = None,
    proposal_id: Any = None,
    goal: Any = None,
    authorization: Any = None,
    scope_gate: Any = None,
    metadata: Any = None,
) -> Dict[str, Any]:
    safe_authorization = authorization if isinstance(authorization, Mapping) else {}
    safe_scope_gate = scope_gate if isinstance(scope_gate, Mapping) else {}
    safe_metadata = metadata if isinstance(metadata, Mapping) else {}

    resolved_task_id = _first_nonempty(
        task_id,
        safe_authorization.get("task_id"),
        safe_scope_gate.get("task_id"),
        "unknown_task",
    )
    resolved_proposal_id = _first_nonempty(
        proposal_id,
        safe_authorization.get("proposal_id"),
        safe_scope_gate.get("proposal_id"),
        "unknown_proposal",
    )
    resolved_goal = _first_nonempty(goal, safe_metadata.get("goal"))

    transaction = {
        "transaction_type": RUNTIME_REPAIR_TRANSACTION_TYPE,
        "transaction_version": RUNTIME_REPAIR_TRANSACTION_VERSION,
        "transaction_id": "",
        "task_id": resolved_task_id,
        "proposal_id": resolved_proposal_id,
        "goal": resolved_goal,
        "state": "created",
        "staged_mutations": [],
        "committed_mutations": [],
        "rolled_back_mutations": [],
        "audit_events": [],
        "snapshot_artifacts": [],
        "authorization": clone_runtime_export(safe_authorization),
        "scope_gate": clone_runtime_export(safe_scope_gate),
        "metadata": clone_runtime_export(safe_metadata),
        "summary": "Runtime repair transaction created.",
    }

    transaction["transaction_id"] = _build_transaction_id(transaction)
    _append_audit_event(
        transaction,
        event_type="transaction_created",
        status="created",
        summary="Runtime repair transaction created.",
    )
    return freeze_runtime_export(transaction)


def stage_runtime_repair_mutation(
    transaction: Any,
    mutation: Any,
) -> Dict[str, Any]:
    tx = _mutable_transaction(transaction)

    if _is_terminal_state(tx.get("state")):
        return _blocked_transaction(
            tx,
            reason="cannot_stage_mutation_after_terminal_state",
            summary="Cannot stage repair mutation after transaction reached terminal state.",
        )

    safe_mutation = mutation if isinstance(mutation, Mapping) else {}
    mutation_record = _build_mutation_record(
        safe_mutation,
        index=len(_list_or_empty(tx.get("staged_mutations"))) + 1,
    )

    staged = _list_or_empty(tx.get("staged_mutations"))
    staged.append(mutation_record)
    tx["staged_mutations"] = staged
    tx["state"] = "staged"
    tx["summary"] = f"Runtime repair transaction staged {len(staged)} mutation(s)."

    _append_audit_event(
        tx,
        event_type="mutation_staged",
        status="staged",
        summary=f"Staged repair mutation {mutation_record['mutation_id']}.",
        details={"mutation": mutation_record},
    )

    return freeze_runtime_export(tx)


def commit_runtime_repair_transaction(
    transaction: Any,
    *,
    audit_registry: Optional[RuntimeAuditRegistry] = None,
    task_snapshot: Any = None,
) -> Dict[str, Any]:
    tx = _mutable_transaction(transaction)

    if _is_terminal_state(tx.get("state")):
        return _blocked_transaction(
            tx,
            reason="cannot_commit_terminal_transaction",
            summary="Cannot commit repair transaction after terminal state.",
        )

    if not _scope_allows_preview(tx):
        return _blocked_transaction(
            tx,
            reason="scope_gate_not_allowed",
            summary="Cannot commit repair transaction because scope gate is blocked.",
        )

    staged = _list_or_empty(tx.get("staged_mutations"))
    if not staged:
        return _blocked_transaction(
            tx,
            reason="no_staged_mutations",
            summary="Cannot commit repair transaction without staged mutations.",
        )

    if bool(tx.get("requires_approval", False)) and str(tx.get("state") or "").strip().lower() not in {
        "approved",
        "authorized",
    }:
        tx["state"] = "awaiting_review"
        tx["summary"] = "Runtime repair transaction awaiting review approval."

        _append_audit_event(
            tx,
            event_type="transaction_awaiting_review",
            status="awaiting_review",
            summary=tx["summary"],
            details={
                "staged_mutation_count": len(staged),
                "requires_approval": True,
            },
        )

        return freeze_runtime_export(tx)

    tx["committed_mutations"] = clone_runtime_export(staged)
    tx["state"] = "committed"
    tx["summary"] = f"Runtime repair transaction committed {len(staged)} staged mutation(s)."

    _append_audit_event(
        tx,
        event_type="transaction_committed",
        status="committed",
        summary=tx["summary"],
        details={"committed_mutation_count": len(staged)},
    )

    if task_snapshot is not None:
        artifact = register_runtime_repair_transaction_snapshot(
            tx,
            task_snapshot=task_snapshot,
            audit_registry=audit_registry,
        )
        snapshots = _list_or_empty(tx.get("snapshot_artifacts"))
        snapshots.append(artifact)
        tx["snapshot_artifacts"] = snapshots

    return freeze_runtime_export(tx)


def rollback_runtime_repair_transaction(
    transaction: Any,
    *,
    reason: Any = "",
    rollback_result: Any = None,
    audit_registry: Optional[RuntimeAuditRegistry] = None,
    task_snapshot: Any = None,
) -> Dict[str, Any]:
    tx = _mutable_transaction(transaction)

    if _is_terminal_state(tx.get("state")) and str(tx.get("state")) != "committed":
        return _blocked_transaction(
            tx,
            reason="cannot_rollback_terminal_transaction",
            summary="Cannot rollback repair transaction after terminal state.",
        )

    staged = _list_or_empty(tx.get("staged_mutations"))
    committed = _list_or_empty(tx.get("committed_mutations"))
    rollback_source = committed or staged

    tx["rolled_back_mutations"] = clone_runtime_export(rollback_source)
    tx["rollback_reason"] = _first_nonempty(reason, "manual_runtime_repair_transaction_rollback")
    tx["rollback_result"] = clone_runtime_export(rollback_result) if isinstance(rollback_result, Mapping) else {}
    tx["state"] = "rolled_back"
    tx["summary"] = f"Runtime repair transaction rolled back {len(rollback_source)} mutation(s)."

    _append_audit_event(
        tx,
        event_type="transaction_rolled_back",
        status="rolled_back",
        summary=tx["summary"],
        details={
            "rollback_reason": tx["rollback_reason"],
            "rolled_back_mutation_count": len(rollback_source),
            "rollback_result": tx["rollback_result"],
        },
    )

    if task_snapshot is not None:
        artifact = register_runtime_repair_transaction_snapshot(
            tx,
            task_snapshot=task_snapshot,
            audit_registry=audit_registry,
        )
        snapshots = _list_or_empty(tx.get("snapshot_artifacts"))
        snapshots.append(artifact)
        tx["snapshot_artifacts"] = snapshots

    return freeze_runtime_export(tx)


def register_runtime_repair_transaction_snapshot(
    transaction: Any,
    *,
    task_snapshot: Any,
    audit_registry: Optional[RuntimeAuditRegistry] = None,
) -> Dict[str, Any]:
    tx = transaction if isinstance(transaction, Mapping) else {}
    snapshot_source = task_snapshot if isinstance(task_snapshot, Mapping) else {}

    merged_snapshot = dict(snapshot_source)
    merged_snapshot.setdefault("task_id", _first_nonempty(tx.get("task_id"), snapshot_source.get("task_id")))
    merged_snapshot.setdefault("status", _first_nonempty(tx.get("state"), snapshot_source.get("status"), "unknown"))
    merged_snapshot.setdefault("goal", _first_nonempty(tx.get("goal"), snapshot_source.get("goal")))
    merged_snapshot["repair_transaction"] = clone_runtime_export(tx)
    merged_snapshot["repair_events"] = _list_or_empty(tx.get("audit_events"))

    replay_snapshot = build_runtime_replay_snapshot(merged_snapshot)
    artifact = build_runtime_audit_artifact(replay_snapshot)

    if audit_registry is not None:
        return audit_registry.register_runtime_audit_artifact(artifact)

    return artifact


def summarize_runtime_repair_transaction(transaction: Any) -> Dict[str, Any]:
    tx = transaction if isinstance(transaction, Mapping) else {}
    staged = _list_or_empty(tx.get("staged_mutations"))
    committed = _list_or_empty(tx.get("committed_mutations"))
    rolled_back = _list_or_empty(tx.get("rolled_back_mutations"))
    events = _list_or_empty(tx.get("audit_events"))

    return {
        "transaction_id": _first_nonempty(tx.get("transaction_id")),
        "task_id": _first_nonempty(tx.get("task_id")),
        "proposal_id": _first_nonempty(tx.get("proposal_id")),
        "state": _first_nonempty(tx.get("state"), "unknown"),
        "staged_mutation_count": len(staged),
        "committed_mutation_count": len(committed),
        "rolled_back_mutation_count": len(rolled_back),
        "audit_event_count": len(events),
        "summary": _first_nonempty(tx.get("summary"), "Runtime repair transaction summary unavailable."),
    }


def _mutable_transaction(transaction: Any) -> Dict[str, Any]:
    tx = clone_runtime_export(transaction) if isinstance(transaction, Mapping) else {}
    tx.setdefault("transaction_type", RUNTIME_REPAIR_TRANSACTION_TYPE)
    tx.setdefault("transaction_version", RUNTIME_REPAIR_TRANSACTION_VERSION)
    tx.setdefault("transaction_id", _build_transaction_id(tx))
    tx.setdefault("task_id", "unknown_task")
    tx.setdefault("proposal_id", "unknown_proposal")
    tx.setdefault("goal", "")
    tx.setdefault("state", "created")
    tx.setdefault("staged_mutations", [])
    tx.setdefault("committed_mutations", [])
    tx.setdefault("rolled_back_mutations", [])
    tx.setdefault("audit_events", [])
    tx.setdefault("snapshot_artifacts", [])
    tx.setdefault("authorization", {})
    tx.setdefault("scope_gate", {})
    tx.setdefault("metadata", {})
    tx.setdefault("summary", "")
    return tx


def _build_mutation_record(mutation: Mapping[str, Any], *, index: int) -> Dict[str, Any]:
    action = _first_nonempty(mutation.get("action"), mutation.get("type"), "unknown_action")
    target_path = _first_nonempty(mutation.get("target_path"), mutation.get("path"), mutation.get("file_path"))
    payload = {
        "index": index,
        "action": action,
        "target_path": target_path,
        "content_hash": _hash_payload(mutation.get("content")),
        "raw_mutation": make_json_safe(mutation),
    }
    mutation_id = _build_stable_id("repair_mutation", payload)
    return {
        "mutation_id": mutation_id,
        "index": index,
        "action": action,
        "target_path": target_path,
        "content_hash": payload["content_hash"],
        "raw_mutation": clone_runtime_export(mutation),
    }


def _append_audit_event(
    transaction: Dict[str, Any],
    *,
    event_type: str,
    status: str,
    summary: str,
    details: Any = None,
) -> None:
    events = _list_or_empty(transaction.get("audit_events"))
    event = {
        "event_type": event_type,
        "status": status,
        "transaction_id": _first_nonempty(transaction.get("transaction_id")),
        "task_id": _first_nonempty(transaction.get("task_id")),
        "proposal_id": _first_nonempty(transaction.get("proposal_id")),
        "summary": summary,
        "details": clone_runtime_export(details) if isinstance(details, Mapping) else {},
        "event_index": len(events) + 1,
    }
    events.append(event)
    transaction["audit_events"] = events


def _blocked_transaction(transaction: Dict[str, Any], *, reason: str, summary: str) -> Dict[str, Any]:
    transaction["state"] = "blocked"
    transaction["blocked_reason"] = reason
    transaction["summary"] = summary
    _append_audit_event(
        transaction,
        event_type="transaction_blocked",
        status="blocked",
        summary=summary,
        details={"reason": reason},
    )
    return freeze_runtime_export(transaction)


def _scope_allows_preview(transaction: Mapping[str, Any]) -> bool:
    scope_gate = transaction.get("scope_gate")
    if not isinstance(scope_gate, Mapping):
        return True

    if "scope_allowed" not in scope_gate:
        return True

    return bool(scope_gate.get("scope_allowed"))


def _is_terminal_state(state: Any) -> bool:
    return str(state or "").strip().lower() in TERMINAL_TRANSACTION_STATES


def _build_transaction_id(transaction: Mapping[str, Any]) -> str:
    task_id = _first_nonempty(transaction.get("task_id"), "unknown_task")
    proposal_id = _first_nonempty(transaction.get("proposal_id"), "unknown_proposal")
    payload = {
        "type": transaction.get("transaction_type") or RUNTIME_REPAIR_TRANSACTION_TYPE,
        "version": transaction.get("transaction_version") or RUNTIME_REPAIR_TRANSACTION_VERSION,
        "task_id": task_id,
        "proposal_id": proposal_id,
        "goal": transaction.get("goal"),
        "metadata": transaction.get("metadata"),
    }
    digest = _hash_payload(payload)[:12]
    return f"runtime_repair_tx:{task_id}:{proposal_id}:{digest}"


def _build_stable_id(prefix: str, payload: Any) -> str:
    return f"{prefix}:{_hash_payload(payload)[:12]}"


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(make_json_safe(payload), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()


def _list_or_empty(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    return []


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""