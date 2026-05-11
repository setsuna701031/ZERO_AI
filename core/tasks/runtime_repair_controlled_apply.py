from __future__ import annotations

from typing import Any, Dict, List, Mapping

from core.tasks.runtime_repair_mutation_authorization import (
    build_runtime_repair_mutation_authorization,
)

from core.tasks.runtime_repair_mutation_scope_gate import (
    build_runtime_repair_mutation_scope_gate,
)

from core.tasks.runtime_repair_transaction_state_machine import (
    can_runtime_repair_transaction_transition,
)

from core.tasks.runtime_state_hygiene import (
    freeze_runtime_export,
)


RUNTIME_REPAIR_CONTROLLED_APPLY_TYPE = (
    "runtime_repair_controlled_apply"
)

RUNTIME_REPAIR_CONTROLLED_APPLY_VERSION = (
    "runtime_repair_controlled_apply.v1"
)


def build_runtime_repair_controlled_apply(
    transaction: Any,
    review_action: Any,
    *,
    target_paths: List[Any] | None = None,
    requested_actions: List[Any] | None = None,
) -> Dict[str, Any]:
    """
    Deterministic apply planning layer.

    This layer NEVER:
    - writes files
    - applies patches
    - runs commands
    - schedules tasks
    - mutates runtime state

    It only builds an apply/rollback plan.
    """

    tx = (
        transaction
        if isinstance(transaction, Mapping)
        else {}
    )

    action = (
        review_action
        if isinstance(review_action, Mapping)
        else {}
    )

    current_state = _safe_text(
        tx.get("state")
    )

    review_state = _safe_text(
        action.get("review_state")
    )

    review_ok = bool(
        action.get("review_ok")
    )

    confirmation = (
        action.get("approval")
        if isinstance(
            action.get("approval"),
            Mapping,
        )
        else {}
    )

    authorization = (
        build_runtime_repair_mutation_authorization(
            confirmation
        )
    )

    scope_gate = (
        build_runtime_repair_mutation_scope_gate(
            authorization,
            target_paths=(
                target_paths
            ),
            requested_actions=(
                requested_actions
            ),
        )
    )

    transition_allowed = (
        can_runtime_repair_transaction_transition(
            current_state,
            "authorized",
        )
    )

    apply_allowed = (
        review_state == "approved"
        and review_ok
        and authorization.get(
            "authorized"
        )
        and scope_gate.get(
            "scope_allowed"
        )
        and transition_allowed
    )

    apply_plan = (
        build_runtime_repair_apply_plan(
            tx,
            authorization=authorization,
            scope_gate=scope_gate,
            target_paths=target_paths,
            requested_actions=requested_actions,
        )
    )

    rollback_plan = (
        build_runtime_repair_rollback_plan(
            tx,
            apply_plan=apply_plan,
        )
    )

    blocked_reasons: List[str] = []

    if review_state != "approved":
        blocked_reasons.append(
            "review_not_approved"
        )

    if not review_ok:
        blocked_reasons.append(
            "review_not_ok"
        )

    if not authorization.get(
        "authorized"
    ):
        blocked_reasons.append(
            "mutation_authorization_blocked"
        )

    if not scope_gate.get(
        "scope_allowed"
    ):
        blocked_reasons.append(
            "scope_gate_blocked"
        )

    if not transition_allowed:
        blocked_reasons.append(
            "illegal_state_transition"
        )

    result = {
        "apply_type": (
            RUNTIME_REPAIR_CONTROLLED_APPLY_TYPE
        ),
        "apply_version": (
            RUNTIME_REPAIR_CONTROLLED_APPLY_VERSION
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
        "current_state": current_state,
        "target_state": "authorized",
        "apply_allowed": apply_allowed,
        "execution_allowed": False,
        "mutation_execution_allowed": False,
        "transition_allowed": (
            transition_allowed
        ),
        "review_state": review_state,
        "authorization": (
            freeze_runtime_export(
                authorization
            )
        ),
        "scope_gate": (
            freeze_runtime_export(
                scope_gate
            )
        ),
        "apply_plan": (
            freeze_runtime_export(
                apply_plan
            )
        ),
        "rollback_plan": (
            freeze_runtime_export(
                rollback_plan
            )
        ),
        "blocked_reasons": (
            sorted(
                list(
                    set(blocked_reasons)
                )
            )
        ),
        "human_summary": (
            build_runtime_repair_apply_summary(
                apply_allowed,
                blocked_reasons,
            )
        ),
    }

    return freeze_runtime_export(
        result
    )


def build_runtime_repair_apply_plan(
    transaction: Mapping[str, Any],
    *,
    authorization: Mapping[str, Any],
    scope_gate: Mapping[str, Any],
    target_paths: List[Any] | None = None,
    requested_actions: List[Any] | None = None,
) -> Dict[str, Any]:
    staged_mutations = (
        transaction.get(
            "staged_mutations"
        )
        if isinstance(
            transaction.get(
                "staged_mutations"
            ),
            list,
        )
        else []
    )

    normalized_targets = (
        _normalize_string_list(
            target_paths
        )
    )

    normalized_actions = (
        _normalize_string_list(
            requested_actions
        )
    )

    return freeze_runtime_export(
        {
            "plan_type": (
                "runtime_repair_apply_plan"
            ),
            "mutation_count": (
                len(staged_mutations)
            ),
            "target_paths": (
                normalized_targets
            ),
            "requested_actions": (
                normalized_actions
            ),
            "authorization_status": (
                authorization.get(
                    "authorization_status"
                )
            ),
            "scope_status": (
                scope_gate.get(
                    "scope_status"
                )
            ),
            "dry_run_only": True,
            "apply_blocked_by_default": True,
        }
    )


def build_runtime_repair_rollback_plan(
    transaction: Mapping[str, Any],
    *,
    apply_plan: Mapping[str, Any],
) -> Dict[str, Any]:
    staged_mutations = (
        transaction.get(
            "staged_mutations"
        )
        if isinstance(
            transaction.get(
                "staged_mutations"
            ),
            list,
        )
        else []
    )

    rollback_steps = []

    for mutation in staged_mutations:
        if not isinstance(
            mutation,
            Mapping,
        ):
            continue

        rollback_steps.append(
            {
                "mutation_id": (
                    mutation.get(
                        "mutation_id"
                    )
                ),
                "rollback_action": (
                    "restore_previous_state"
                ),
                "target_path": (
                    mutation.get(
                        "target_path"
                    )
                ),
            }
        )

    return freeze_runtime_export(
        {
            "plan_type": (
                "runtime_repair_rollback_plan"
            ),
            "rollback_step_count": (
                len(rollback_steps)
            ),
            "rollback_steps": (
                rollback_steps
            ),
            "linked_apply_plan": (
                apply_plan.get(
                    "plan_type"
                )
            ),
        }
    )


def build_runtime_repair_apply_summary(
    apply_allowed: bool,
    blocked_reasons: List[str],
) -> str:
    if apply_allowed:
        return (
            "Controlled apply plan passed. "
            "Execution remains disabled."
        )

    if not blocked_reasons:
        return (
            "Controlled apply blocked."
        )

    return (
        "Controlled apply blocked: "
        + ", ".join(
            sorted(
                list(
                    set(blocked_reasons)
                )
            )
        )
    )


def _normalize_string_list(
    values: Any,
) -> List[str]:
    if not isinstance(
        values,
        list,
    ):
        return []

    result: List[str] = []

    for value in values:
        text = _safe_text(value)

        if text:
            result.append(text)

    return result


def _safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()