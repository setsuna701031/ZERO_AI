from __future__ import annotations

from typing import Any, Dict, List, Mapping, Set

from core.tasks.runtime_state_hygiene import (
    freeze_runtime_export,
)


RUNTIME_REPAIR_TRANSACTION_STATES = {
    "created",
    "staged",
    "awaiting_review",
    "approved",
    "authorized",
    "committed",
    "rolled_back",
    "blocked",
    "failed",
    "archived",
}


RUNTIME_REPAIR_TERMINAL_STATES = {
    "committed",
    "rolled_back",
    "blocked",
    "failed",
    "archived",
}


RUNTIME_REPAIR_TRANSACTION_TRANSITIONS = {
    "created": {
        "staged",
        "blocked",
        "failed",
        "archived",
    },
    "staged": {
        "awaiting_review",
        "rolled_back",
        "blocked",
        "failed",
        "archived",
    },
    "awaiting_review": {
        "approved",
        "rolled_back",
        "blocked",
        "failed",
        "archived",
    },
    "approved": {
        "authorized",
        "rolled_back",
        "blocked",
        "failed",
        "archived",
    },
    "authorized": {
        "committed",
        "rolled_back",
        "blocked",
        "failed",
        "archived",
    },
    "committed": set(),
    "rolled_back": set(),
    "blocked": set(),
    "failed": set(),
    "archived": set(),
}


def normalize_runtime_repair_transaction_state(
    state: Any,
) -> str:
    normalized = str(state or "").strip().lower()

    if normalized in RUNTIME_REPAIR_TRANSACTION_STATES:
        return normalized

    return "unknown"


def is_runtime_repair_transaction_terminal_state(
    state: Any,
) -> bool:
    normalized = (
        normalize_runtime_repair_transaction_state(
            state
        )
    )

    return (
        normalized
        in RUNTIME_REPAIR_TERMINAL_STATES
    )


def get_runtime_repair_transaction_allowed_transitions(
    state: Any,
) -> Set[str]:
    normalized = (
        normalize_runtime_repair_transaction_state(
            state
        )
    )

    return set(
        RUNTIME_REPAIR_TRANSACTION_TRANSITIONS.get(
            normalized,
            set(),
        )
    )


def can_runtime_repair_transaction_transition(
    current_state: Any,
    next_state: Any,
) -> bool:
    current_normalized = (
        normalize_runtime_repair_transaction_state(
            current_state
        )
    )

    next_normalized = (
        normalize_runtime_repair_transaction_state(
            next_state
        )
    )

    if (
        current_normalized
        not in RUNTIME_REPAIR_TRANSACTION_STATES
    ):
        return False

    if (
        next_normalized
        not in RUNTIME_REPAIR_TRANSACTION_STATES
    ):
        return False

    allowed = (
        get_runtime_repair_transaction_allowed_transitions(
            current_normalized
        )
    )

    return next_normalized in allowed


def build_runtime_repair_transaction_transition(
    *,
    transaction_id: Any,
    task_id: Any,
    proposal_id: Any,
    current_state: Any,
    next_state: Any,
    reason: Any = "",
) -> Dict[str, Any]:
    current_normalized = (
        normalize_runtime_repair_transaction_state(
            current_state
        )
    )

    next_normalized = (
        normalize_runtime_repair_transaction_state(
            next_state
        )
    )

    allowed = (
        can_runtime_repair_transaction_transition(
            current_normalized,
            next_normalized,
        )
    )

    transition = {
        "transition_type": (
            "runtime_repair_transaction_transition"
        ),
        "transaction_id": _safe_text(
            transaction_id
        ),
        "task_id": _safe_text(task_id),
        "proposal_id": _safe_text(
            proposal_id
        ),
        "current_state": current_normalized,
        "next_state": next_normalized,
        "transition_allowed": allowed,
        "reason": _safe_text(reason),
        "terminal_transition": (
            is_runtime_repair_transaction_terminal_state(
                next_normalized
            )
        ),
    }

    if allowed:
        transition["transition_status"] = "allowed"
    else:
        transition["transition_status"] = "blocked"

    return freeze_runtime_export(
        transition
    )


def summarize_runtime_repair_transaction_state_machine(
    state: Any,
) -> Dict[str, Any]:
    normalized = (
        normalize_runtime_repair_transaction_state(
            state
        )
    )

    return freeze_runtime_export(
        {
            "state": normalized,
            "terminal": (
                is_runtime_repair_transaction_terminal_state(
                    normalized
                )
            ),
            "allowed_transitions": sorted(
                list(
                    get_runtime_repair_transaction_allowed_transitions(
                        normalized
                    )
                )
            ),
        }
    )


def _safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()