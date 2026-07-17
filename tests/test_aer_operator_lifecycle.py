from __future__ import annotations

from core.runtime.aer_operator_lifecycle import (
    AER_OPERATOR_LIFECYCLE_CONTRACT,
    OPERATOR_ALLOWED_TRANSITIONS,
    OPERATOR_PHASES,
    build_operator_lifecycle_record,
    can_transition_operator_phase,
    is_operator_terminal_phase,
    normalize_operator_phase,
    validate_operator_lifecycle_record,
)


def test_build_operator_lifecycle_record_contains_contract_and_identity() -> None:
    payload = build_operator_lifecycle_record(
        operator_session_id="operator-session-1",
        package_id="package-79",
    )

    assert payload["contract"] == AER_OPERATOR_LIFECYCLE_CONTRACT
    assert payload["operator_session_id"] == "operator-session-1"
    assert payload["package_id"] == "package-79"
    assert payload["phase"] == "initialized"


def test_validate_operator_lifecycle_record_accepts_minimal_initialized_record() -> None:
    payload = build_operator_lifecycle_record(
        operator_session_id="operator-session-1",
        package_id="package-79",
    )

    result = validate_operator_lifecycle_record(payload)

    assert result["ok"] is True
    assert result["errors"] == []


def test_validate_operator_lifecycle_record_rejects_non_dict_payload() -> None:
    result = validate_operator_lifecycle_record(None)

    assert result["ok"] is False
    assert "payload must be a dict" in result["errors"]


def test_validate_operator_lifecycle_record_rejects_missing_identity() -> None:
    payload = build_operator_lifecycle_record(
        operator_session_id="",
        package_id="package-79",
    )

    result = validate_operator_lifecycle_record(payload)

    assert result["ok"] is False
    assert "operator_session_id is required" in result["errors"]


def test_validate_operator_lifecycle_record_rejects_missing_package_id() -> None:
    payload = build_operator_lifecycle_record(
        operator_session_id="operator-session-1",
        package_id="",
    )

    result = validate_operator_lifecycle_record(payload)

    assert result["ok"] is False
    assert "package_id is required" in result["errors"]


def test_validate_operator_lifecycle_record_rejects_invalid_contract() -> None:
    payload = build_operator_lifecycle_record(
        operator_session_id="operator-session-1",
        package_id="package-79",
    )
    payload["contract"] = "wrong.contract"

    result = validate_operator_lifecycle_record(payload)

    assert result["ok"] is False
    assert "invalid contract" in result["errors"]


def test_normalize_operator_phase_defaults_unknown_to_initialized() -> None:
    assert normalize_operator_phase("RUNNING") == "running"
    assert normalize_operator_phase("not-a-phase") == "initialized"


def test_all_operator_phases_normalize_to_themselves() -> None:
    for phase in OPERATOR_PHASES:
        assert normalize_operator_phase(phase) == phase


def test_allowed_transition_table_does_not_allow_terminal_escape() -> None:
    assert OPERATOR_ALLOWED_TRANSITIONS["completed"] == ()
    assert OPERATOR_ALLOWED_TRANSITIONS["failed"] == ()
    assert OPERATOR_ALLOWED_TRANSITIONS["blocked"] == ()


def test_can_transition_operator_phase_accepts_mainline_path() -> None:
    assert can_transition_operator_phase("initialized", "admitted") is True
    assert can_transition_operator_phase("admitted", "running") is True
    assert can_transition_operator_phase("running", "checkpointed") is True
    assert can_transition_operator_phase("checkpointed", "resumed") is True
    assert can_transition_operator_phase("resumed", "running") is True
    assert can_transition_operator_phase("running", "completed") is True


def test_can_transition_operator_phase_rejects_invalid_jump() -> None:
    assert can_transition_operator_phase("initialized", "completed") is False
    assert can_transition_operator_phase("completed", "running") is False
    assert can_transition_operator_phase("failed", "running") is False
    assert can_transition_operator_phase("blocked", "running") is False


def test_terminal_phase_helper() -> None:
    assert is_operator_terminal_phase("completed") is True
    assert is_operator_terminal_phase("failed") is True
    assert is_operator_terminal_phase("blocked") is True
    assert is_operator_terminal_phase("running") is False


def test_validate_operator_lifecycle_record_accepts_valid_transition() -> None:
    payload = build_operator_lifecycle_record(
        operator_session_id="operator-session-1",
        package_id="package-79",
        previous_phase="initialized",
        phase="admitted",
        transition_reason="package admitted",
    )

    result = validate_operator_lifecycle_record(payload)

    assert result["ok"] is True


def test_validate_operator_lifecycle_record_rejects_invalid_transition() -> None:
    payload = build_operator_lifecycle_record(
        operator_session_id="operator-session-1",
        package_id="package-79",
        previous_phase="initialized",
        phase="completed",
        transition_reason="invalid jump",
    )

    result = validate_operator_lifecycle_record(payload)

    assert result["ok"] is False
    assert "invalid transition: initialized -> completed" in result["errors"]