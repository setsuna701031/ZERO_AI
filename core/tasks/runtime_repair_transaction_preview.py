from __future__ import annotations

from typing import Any, Dict, List, Mapping

from core.tasks.runtime_state_hygiene import freeze_runtime_export


RUNTIME_REPAIR_TRANSACTION_PREVIEW_TYPE = (
    "runtime_repair_transaction_preview"
)

RUNTIME_REPAIR_TRANSACTION_PREVIEW_VERSION = (
    "runtime_repair_transaction_preview.v1"
)


def build_runtime_repair_transaction_preview(
    transaction: Any,
) -> Dict[str, Any]:
    """Build a deterministic preview payload from a repair transaction.

    This layer is read-only and side-effect free.
    It does not execute tools, apply patches, write files,
    schedule tasks, or mutate runtime state.
    """
    tx = transaction if isinstance(transaction, Mapping) else {}

    staged_mutations = _safe_list_of_dicts(
        tx.get("staged_mutations")
    )
    committed_mutations = _safe_list_of_dicts(
        tx.get("committed_mutations")
    )
    rolled_back_mutations = _safe_list_of_dicts(
        tx.get("rolled_back_mutations")
    )

    scope_gate = (
        tx.get("scope_gate")
        if isinstance(tx.get("scope_gate"), Mapping)
        else {}
    )

    audit_events = _safe_list_of_dicts(
        tx.get("audit_events")
    )

    risk_level = classify_runtime_repair_preview_risk(
        tx,
        staged_mutations=staged_mutations,
    )

    commit_ready = is_runtime_repair_preview_commit_ready(
        tx,
        staged_mutations=staged_mutations,
    )

    rollback_ready = is_runtime_repair_preview_rollback_ready(
        tx,
    )

    preview = {
        "preview_type": (
            RUNTIME_REPAIR_TRANSACTION_PREVIEW_TYPE
        ),
        "preview_version": (
            RUNTIME_REPAIR_TRANSACTION_PREVIEW_VERSION
        ),
        "transaction_id": _safe_text(
            tx.get("transaction_id")
        ),
        "task_id": _safe_text(
            tx.get("task_id")
        ),
        "proposal_id": _safe_text(
            tx.get("proposal_id")
        ),
        "state": _safe_text(
            tx.get("state")
        ),
        "goal": _safe_text(
            tx.get("goal")
        ),
        "summary": _safe_text(
            tx.get("summary")
        ),
        "risk_level": risk_level,
        "commit_ready": commit_ready,
        "rollback_ready": rollback_ready,
        "scope_status": _safe_text(
            scope_gate.get("scope_status")
        ),
        "scope_allowed": bool(
            scope_gate.get("scope_allowed", True)
        ),
        "blocked_reasons": _safe_list(
            scope_gate.get("blocked_reasons")
        ),
        "mutation_counts": {
            "staged": len(staged_mutations),
            "committed": len(committed_mutations),
            "rolled_back": len(rolled_back_mutations),
        },
        "mutation_preview": (
            build_runtime_repair_mutation_preview(
                staged_mutations
            )
        ),
        "audit_event_preview": (
            build_runtime_repair_audit_preview(
                audit_events
            )
        ),
        "human_summary": (
            build_runtime_repair_preview_summary(
                risk_level=risk_level,
                state=_safe_text(tx.get("state")),
                staged_mutations=staged_mutations,
                blocked_reasons=_safe_list(
                    scope_gate.get("blocked_reasons")
                ),
            )
        ),
    }

    return freeze_runtime_export(preview)


def build_runtime_repair_mutation_preview(
    mutations: Any,
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []

    for mutation in _safe_list_of_dicts(mutations):
        result.append(
            {
                "mutation_id": _safe_text(
                    mutation.get("mutation_id")
                ),
                "action": _safe_text(
                    mutation.get("action")
                ),
                "target_path": _safe_text(
                    mutation.get("target_path")
                ),
                "content_hash": _safe_text(
                    mutation.get("content_hash")
                )[:12],
            }
        )

    return result


def build_runtime_repair_audit_preview(
    audit_events: Any,
) -> List[Dict[str, Any]]:
    events = _safe_list_of_dicts(audit_events)

    result: List[Dict[str, Any]] = []

    for event in events[-5:]:
        result.append(
            {
                "event_type": _safe_text(
                    event.get("event_type")
                ),
                "status": _safe_text(
                    event.get("status")
                ),
                "summary": _compact_text(
                    event.get("summary")
                ),
            }
        )

    return result


def classify_runtime_repair_preview_risk(
    transaction: Any,
    *,
    staged_mutations: List[Dict[str, Any]] | None = None,
) -> str:
    tx = transaction if isinstance(transaction, Mapping) else {}

    scope_gate = (
        tx.get("scope_gate")
        if isinstance(tx.get("scope_gate"), Mapping)
        else {}
    )

    if not bool(scope_gate.get("scope_allowed", True)):
        return "critical"

    staged = (
        staged_mutations
        if isinstance(staged_mutations, list)
        else _safe_list_of_dicts(
            tx.get("staged_mutations")
        )
    )

    if not staged:
        return "low"

    risky_actions = {
        "delete_file",
        "run_shell_command",
        "modify_scheduler",
        "modify_planner",
    }

    medium_actions = {
        "write_file",
        "apply_patch",
    }

    has_medium = False

    for mutation in staged:
        action = _safe_text(
            mutation.get("action")
        ).lower()

        if action in risky_actions:
            return "high"

        if action in medium_actions:
            has_medium = True

        target_path = _safe_text(
            mutation.get("target_path")
        ).lower()

        if any(
            keyword in target_path
            for keyword in (
                "scheduler.py",
                "agent_loop.py",
                "system_boot.py",
            )
        ):
            return "high"

    if has_medium:
        return "medium"

    return "low"


def is_runtime_repair_preview_commit_ready(
    transaction: Any,
    *,
    staged_mutations: List[Dict[str, Any]] | None = None,
) -> bool:
    tx = transaction if isinstance(transaction, Mapping) else {}

    state = _safe_text(
        tx.get("state")
    ).lower()

    if state not in {
        "created",
        "staged",
    }:
        return False

    staged = (
        staged_mutations
        if isinstance(staged_mutations, list)
        else _safe_list_of_dicts(
            tx.get("staged_mutations")
        )
    )

    if not staged:
        return False

    scope_gate = (
        tx.get("scope_gate")
        if isinstance(tx.get("scope_gate"), Mapping)
        else {}
    )

    return bool(
        scope_gate.get("scope_allowed", True)
    )


def is_runtime_repair_preview_rollback_ready(
    transaction: Any,
) -> bool:
    tx = transaction if isinstance(transaction, Mapping) else {}

    state = _safe_text(
        tx.get("state")
    ).lower()

    return state in {
        "staged",
        "committed",
        "failed",
        "blocked",
    }


def build_runtime_repair_preview_summary(
    *,
    risk_level: str,
    state: str,
    staged_mutations: List[Dict[str, Any]],
    blocked_reasons: List[str],
) -> str:
    mutation_count = len(staged_mutations)

    summary = (
        f"Repair transaction is {state or 'unknown'} "
        f"with {mutation_count} staged mutation(s). "
        f"Risk level: {risk_level}."
    )

    if blocked_reasons:
        summary += (
            " Blocked reasons: "
            + ", ".join(blocked_reasons)
            + "."
        )

    return summary


def _safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _compact_text(
    value: Any,
    max_len: int = 220,
) -> str:
    text = _safe_text(value)

    if not text:
        return ""

    text = " ".join(text.split())

    if len(text) <= max_len:
        return text

    return text[: max_len - 3].rstrip() + "..."


def _safe_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []

    result: List[str] = []

    for item in value:
        text = _safe_text(item)

        if text:
            result.append(text)

    return result


def _safe_list_of_dicts(
    value: Any,
) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []

    result: List[Dict[str, Any]] = []

    for item in value:
        if isinstance(item, Mapping):
            result.append(dict(item))

    return result