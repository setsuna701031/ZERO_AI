from __future__ import annotations

from core.runtime.aer_operator_lifecycle import build_operator_lifecycle_record
from core.runtime.aer_operator_state_machine import (
    AER_OPERATOR_STATE_MACHINE_CONTRACT,
    AER_OPERATOR_TRANSITION_CONTRACT,
    advance_operator_lifecycle,
    append_transition_history,
    build_transition_record,
    can_transition,
    terminal_reason,
    transition_history,
    validate_transition_record,
)


def test_can_transition_accepts_allowed_mainline_path() -> None:
    assert can_transition("initialized", "admitted") is True
    assert can_transition("admitted", "running") is True
    assert can_transition("running", "checkpointed") is True
    assert can_transition("checkpointed", "resumed") is True
    assert can_transition("resumed", "running") is True
    assert can_transition("running", "completed") is True


def test_can_transition_rejects_terminal_escape_and_invalid_jump() -> None:
    assert can_transition("completed", "running") is False
    assert can_transition("failed", "running") is False
    assert can_transition("blocked", "running") is False
    assert can_transition("initialized", "completed") is False


def test_build_transition_record_contains_contract_and_allowed_flag() -> None:
    payload = build_transition_record(
        operator_session_id="operator-session-1",
        package_id="package-81",
        from_phase="initialized",
        to_phase="admitted",
        reason="admit package",
    )

    assert payload["contract"] == AER_OPERATOR_TRANSITION_CONTRACT
    assert payload["operator_session_id"] == "operator-session-1"
    assert payload["package_id"] == "package-81"
    assert payload["from_phase"] == "initialized"
    assert payload["to_phase"] == "admitted"
    assert payload["allowed"] is True


def test_validate_transition_record_accepts_valid_transition() -> None:
    payload = build_transition_record(
        operator_session_id="operator-session-1",
        package_id="package-81",
        from_phase="initialized",
        to_phase="admitted",
        reason="admit package",
    )

    result = validate_transition_record(payload)

    assert result["ok"] is True
    assert result["errors"] == []


def test_validate_transition_record_rejects_non_dict_payload() -> None:
    result = validate_transition_record(None)

    assert result["ok"] is False
    assert "payload must be a dict" in result["errors"]


def test_validate_transition_record_rejects_missing_identity() -> None:
    payload = build_transition_record(
        operator_session_id="",
        package_id="",
        from_phase="initialized",
        to_phase="admitted",
    )

    result = validate_transition_record(payload)

    assert result["ok"] is False
    assert "operator_session_id is required" in result["errors"]
    assert "package_id is required" in result["errors"]


def test_validate_transition_record_rejects_invalid_transition() -> None:
    payload = build_transition_record(
        operator_session_id="operator-session-1",
        package_id="package-81",
        from_phase="initialized",
        to_phase="completed",
        reason="invalid jump",
    )

    result = validate_transition_record(payload)

    assert result["ok"] is False
    assert "transition not allowed: initialized -> completed" in result["errors"]


def test_validate_transition_record_rejects_allowed_flag_mismatch() -> None:
    payload = build_transition_record(
        operator_session_id="operator-session-1",
        package_id="package-81",
        from_phase="initialized",
        to_phase="admitted",
    )
    payload["allowed"] = False

    result = validate_transition_record(payload)

    assert result["ok"] is False
    assert "allowed flag mismatch" in result["errors"]


def test_validate_transition_record_rejects_negative_sequence() -> None:
    payload = build_transition_record(
        operator_session_id="operator-session-1",
        package_id="package-81",
        from_phase="initialized",
        to_phase="admitted",
        sequence=-1,
    )

    result = validate_transition_record(payload)

    assert result["ok"] is False
    assert "sequence must be >= 0" in result["errors"]


def test_advance_operator_lifecycle_updates_phase_and_history() -> None:
    record = build_operator_lifecycle_record(
        operator_session_id="operator-session-1",
        package_id="package-81",
    )

    result = advance_operator_lifecycle(
        record,
        "admitted",
        reason="package admitted",
    )

    assert result["ok"] is True
    assert result["contract"] == AER_OPERATOR_STATE_MACHINE_CONTRACT
    assert result["record"]["previous_phase"] == "initialized"
    assert result["record"]["phase"] == "admitted"
    assert result["record"]["transition_reason"] == "package admitted"
    assert len(result["record"]["transition_history"]) == 1
    assert result["transition"]["from_phase"] == "initialized"
    assert result["transition"]["to_phase"] == "admitted"


def test_advance_operator_lifecycle_rejects_invalid_transition() -> None:
    record = build_operator_lifecycle_record(
        operator_session_id="operator-session-1",
        package_id="package-81",
    )

    result = advance_operator_lifecycle(
        record,
        "completed",
        reason="invalid jump",
    )

    assert result["ok"] is False
    assert "transition not allowed: initialized -> completed" in result["errors"]


def test_advance_operator_lifecycle_rejects_invalid_lifecycle_record() -> None:
    record = build_operator_lifecycle_record(
        operator_session_id="",
        package_id="package-81",
    )

    result = advance_operator_lifecycle(record, "admitted")

    assert result["ok"] is False
    assert "operator_session_id is required" in result["errors"]


def test_append_transition_history_preserves_original_record() -> None:
    record = build_operator_lifecycle_record(
        operator_session_id="operator-session-1",
        package_id="package-81",
    )
    transition = build_transition_record(
        operator_session_id="operator-session-1",
        package_id="package-81",
        from_phase="initialized",
        to_phase="admitted",
    )

    next_record = append_transition_history(record, transition)

    assert "transition_history" not in record
    assert len(next_record["transition_history"]) == 1


def test_transition_history_returns_copy() -> None:
    record = build_operator_lifecycle_record(
        operator_session_id="operator-session-1",
        package_id="package-81",
    )
    transition = build_transition_record(
        operator_session_id="operator-session-1",
        package_id="package-81",
        from_phase="initialized",
        to_phase="admitted",
    )
    record = append_transition_history(record, transition)

    history = transition_history(record)
    history[0]["to_phase"] = "mutated"

    assert record["transition_history"][0]["to_phase"] == "admitted"


def test_terminal_reason_returns_empty_for_non_terminal_phase() -> None:
    record = build_operator_lifecycle_record(
        operator_session_id="operator-session-1",
        package_id="package-81",
        phase="running",
    )

    assert terminal_reason(record) == ""


def test_terminal_reason_returns_transition_reason_for_terminal_phase() -> None:
    record = build_operator_lifecycle_record(
        operator_session_id="operator-session-1",
        package_id="package-81",
        phase="completed",
        transition_reason="done",
    )

    assert terminal_reason(record) == "done"


def test_advance_operator_lifecycle_can_walk_mainline_sequence() -> None:
    record = build_operator_lifecycle_record(
        operator_session_id="operator-session-1",
        package_id="package-81",
    )

    for next_phase in ("admitted", "running", "checkpointed", "resumed", "running", "completed"):
        result = advance_operator_lifecycle(record, next_phase, reason=f"go {next_phase}")
        assert result["ok"] is True
        record = result["record"]

    assert record["phase"] == "completed"
    assert len(record["transition_history"]) == 6
    assert terminal_reason(record) == "go completed"