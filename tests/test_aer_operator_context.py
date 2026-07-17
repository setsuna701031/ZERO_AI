from __future__ import annotations

from core.runtime.aer_operator_context import (
    AER_OPERATOR_CONTEXT_CONTRACT,
    OPERATOR_CONTEXT_FIELDS,
    build_operator_context,
    copy_operator_context,
    merge_operator_context,
    validate_operator_context,
)


def test_build_operator_context_contains_required_fields() -> None:
    payload = build_operator_context(
        operator_session_id="operator-session-1",
        package_id="package-82",
    )

    assert payload["contract"] == AER_OPERATOR_CONTEXT_CONTRACT
    assert payload["operator_session_id"] == "operator-session-1"
    assert payload["package_id"] == "package-82"
    assert payload["current_phase"] == "initialized"

    for field in OPERATOR_CONTEXT_FIELDS:
        assert field in payload


def test_validate_operator_context_accepts_valid_payload() -> None:
    payload = build_operator_context(
        operator_session_id="operator-session-1",
        package_id="package-82",
        runtime_session_id="runtime-session-1",
        current_phase="running",
        checkpoint_id="checkpoint-1",
        approval_state="not_required",
        stop_reason="",
        issue_report_id="",
        metadata={"source": "test"},
    )

    result = validate_operator_context(payload)

    assert result["ok"] is True
    assert result["errors"] == []


def test_validate_operator_context_rejects_non_dict_payload() -> None:
    result = validate_operator_context(None)

    assert result["ok"] is False
    assert "payload must be a dict" in result["errors"]


def test_validate_operator_context_rejects_missing_required_fields() -> None:
    payload = build_operator_context(
        operator_session_id="operator-session-1",
        package_id="package-82",
    )
    del payload["runtime_session_id"]
    del payload["metadata"]

    result = validate_operator_context(payload)

    assert result["ok"] is False
    assert "missing required field: runtime_session_id" in result["errors"]
    assert "missing required field: metadata" in result["errors"]


def test_validate_operator_context_rejects_missing_identity_fields() -> None:
    payload = build_operator_context(
        operator_session_id="",
        package_id="",
    )

    result = validate_operator_context(payload)

    assert result["ok"] is False
    assert "operator_session_id is required" in result["errors"]
    assert "package_id is required" in result["errors"]


def test_validate_operator_context_rejects_invalid_contract() -> None:
    payload = build_operator_context(
        operator_session_id="operator-session-1",
        package_id="package-82",
    )
    payload["contract"] = "wrong.contract"

    result = validate_operator_context(payload)

    assert result["ok"] is False
    assert "invalid contract" in result["errors"]


def test_validate_operator_context_rejects_invalid_current_phase() -> None:
    payload = build_operator_context(
        operator_session_id="operator-session-1",
        package_id="package-82",
    )
    payload["current_phase"] = "not-a-phase"

    result = validate_operator_context(payload)

    assert result["ok"] is False
    assert "invalid current_phase: not-a-phase" in result["errors"]


def test_validate_operator_context_rejects_non_dict_metadata() -> None:
    payload = build_operator_context(
        operator_session_id="operator-session-1",
        package_id="package-82",
    )
    payload["metadata"] = []

    result = validate_operator_context(payload)

    assert result["ok"] is False
    assert "metadata must be a dict" in result["errors"]


def test_copy_operator_context_returns_deep_copy() -> None:
    payload = build_operator_context(
        operator_session_id="operator-session-1",
        package_id="package-82",
        metadata={"nested": {"value": "original"}},
    )

    copied = copy_operator_context(payload)
    copied["metadata"]["nested"]["value"] = "mutated"

    assert payload["metadata"]["nested"]["value"] == "original"


def test_merge_operator_context_overlays_allowed_fields_and_metadata() -> None:
    payload = build_operator_context(
        operator_session_id="operator-session-1",
        package_id="package-82",
        current_phase="initialized",
        metadata={"kept": True, "changed": "old"},
    )

    merged = merge_operator_context(
        payload,
        {
            "current_phase": "RUNNING",
            "checkpoint_id": "checkpoint-1",
            "metadata": {"changed": "new", "added": True},
            "unknown_field": "ignored",
        },
    )

    assert merged["contract"] == AER_OPERATOR_CONTEXT_CONTRACT
    assert merged["current_phase"] == "running"
    assert merged["checkpoint_id"] == "checkpoint-1"
    assert merged["metadata"] == {"kept": True, "changed": "new", "added": True}
    assert "unknown_field" not in merged
    assert payload["current_phase"] == "initialized"
    assert payload["metadata"] == {"kept": True, "changed": "old"}


def test_merge_operator_context_does_not_perform_state_transition_validation() -> None:
    payload = build_operator_context(
        operator_session_id="operator-session-1",
        package_id="package-82",
        current_phase="initialized",
    )

    merged = merge_operator_context(payload, {"current_phase": "completed"})

    assert merged["current_phase"] == "completed"
    assert validate_operator_context(merged)["ok"] is True
