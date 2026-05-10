from __future__ import annotations

from core.tasks.runtime_repair_transaction_state_machine import (
    build_runtime_repair_transaction_transition,
    can_runtime_repair_transaction_transition,
    get_runtime_repair_transaction_allowed_transitions,
    is_runtime_repair_transaction_terminal_state,
    normalize_runtime_repair_transaction_state,
    summarize_runtime_repair_transaction_state_machine,
)


def test_normalize_runtime_repair_transaction_state() -> None:
    assert (
        normalize_runtime_repair_transaction_state(
            "APPROVED"
        )
        == "approved"
    )

    assert (
        normalize_runtime_repair_transaction_state(
            "unknown_state"
        )
        == "unknown"
    )


def test_is_runtime_repair_transaction_terminal_state() -> None:
    assert (
        is_runtime_repair_transaction_terminal_state(
            "committed"
        )
        is True
    )

    assert (
        is_runtime_repair_transaction_terminal_state(
            "staged"
        )
        is False
    )


def test_get_runtime_repair_transaction_allowed_transitions() -> None:
    transitions = (
        get_runtime_repair_transaction_allowed_transitions(
            "approved"
        )
    )

    assert "authorized" in transitions
    assert "rolled_back" in transitions


def test_can_runtime_repair_transaction_transition() -> None:
    assert (
        can_runtime_repair_transaction_transition(
            "approved",
            "authorized",
        )
        is True
    )

    assert (
        can_runtime_repair_transaction_transition(
            "committed",
            "created",
        )
        is False
    )


def test_build_runtime_repair_transaction_transition_allowed() -> None:
    transition = (
        build_runtime_repair_transaction_transition(
            transaction_id="tx-1",
            task_id="task-1",
            proposal_id="proposal-1",
            current_state="approved",
            next_state="authorized",
            reason="review passed",
        )
    )

    assert (
        transition["transition_allowed"]
        is True
    )

    assert (
        transition["transition_status"]
        == "allowed"
    )


def test_build_runtime_repair_transaction_transition_blocked() -> None:
    transition = (
        build_runtime_repair_transaction_transition(
            transaction_id="tx-1",
            task_id="task-1",
            proposal_id="proposal-1",
            current_state="committed",
            next_state="created",
            reason="illegal rewind",
        )
    )

    assert (
        transition["transition_allowed"]
        is False
    )

    assert (
        transition["transition_status"]
        == "blocked"
    )


def test_summarize_runtime_repair_transaction_state_machine() -> None:
    summary = (
        summarize_runtime_repair_transaction_state_machine(
            "awaiting_review"
        )
    )

    assert (
        summary["state"]
        == "awaiting_review"
    )

    assert (
        summary["terminal"]
        is False
    )

    assert (
        "approved"
        in summary["allowed_transitions"]
    )