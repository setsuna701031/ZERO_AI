from __future__ import annotations

import copy
import inspect

import core.runtime.aer_operator_stop_condition as stop_condition_module
from core.runtime.aer_operator_stop_condition import (
    create_stop_condition,
    resolve_stop_condition,
    stop_condition_to_summary,
    validate_stop_condition,
)


STOP_CONDITION_CONTRACT = "aer.operator_stop_condition.v2"


def test_create_stop_condition_builds_active_contract() -> None:
    stop_condition = create_stop_condition(
        stop_condition_id="stop-1",
        operator_session_id="operator-session-1",
        package_id="package-92",
        reason="blocked",
        message="operator needs human input",
        metadata={"source": "test"},
    )

    assert stop_condition == {
        "contract": STOP_CONDITION_CONTRACT,
        "stop_condition_id": "stop-1",
        "operator_session_id": "operator-session-1",
        "package_id": "package-92",
        "reason": "blocked",
        "status": "active",
        "message": "operator needs human input",
        "metadata": {"source": "test"},
    }
    assert validate_stop_condition(stop_condition)["ok"] is True


def test_create_stop_condition_defaults_metadata_to_dict() -> None:
    stop_condition = create_stop_condition(
        stop_condition_id="stop-1",
        operator_session_id="operator-session-1",
        package_id="package-92",
        reason="completed",
    )

    assert stop_condition["metadata"] == {}
    assert validate_stop_condition(stop_condition)["ok"] is True


def test_resolve_stop_condition_returns_new_resolved_dict_without_mutating_input() -> None:
    stop_condition = create_stop_condition(
        stop_condition_id="stop-1",
        operator_session_id="operator-session-1",
        package_id="package-92",
        reason="waiting_for_approval",
        message="approval pending",
        metadata={"nested": {"value": "original"}},
    )
    original = copy.deepcopy(stop_condition)

    resolved = resolve_stop_condition(
        stop_condition,
        resolved_by="human-1",
        resolution_note="approved to continue",
    )
    resolved["metadata"]["nested"]["value"] = "mutated"

    assert resolved["stop_condition_id"] == "stop-1"
    assert resolved["status"] == "resolved"
    assert resolved["resolved_by"] == "human-1"
    assert resolved["resolution_note"] == "approved to continue"
    assert stop_condition == original
    assert validate_stop_condition(resolved)["ok"] is True


def test_stop_condition_id_is_preserved_when_resolved() -> None:
    stop_condition = create_stop_condition(
        stop_condition_id="stop-immutable",
        operator_session_id="operator-session-1",
        package_id="package-92",
        reason="failed",
    )

    resolved = resolve_stop_condition(stop_condition)

    assert resolved["stop_condition_id"] == "stop-immutable"


def test_validate_stop_condition_rejects_non_dict_payload() -> None:
    result = validate_stop_condition(None)

    assert result["ok"] is False
    assert result["contract"] == STOP_CONDITION_CONTRACT
    assert "payload must be a dict" in result["errors"]


def test_validate_stop_condition_rejects_missing_required_fields() -> None:
    result = validate_stop_condition({})

    assert result["ok"] is False
    for field in (
        "contract",
        "stop_condition_id",
        "operator_session_id",
        "package_id",
        "reason",
        "status",
        "message",
        "metadata",
    ):
        assert f"missing required field: {field}" in result["errors"]


def test_validate_stop_condition_rejects_empty_identity_fields() -> None:
    stop_condition = create_stop_condition(
        stop_condition_id="",
        operator_session_id="",
        package_id="",
        reason="blocked",
    )

    result = validate_stop_condition(stop_condition)

    assert result["ok"] is False
    assert "stop_condition_id is required" in result["errors"]
    assert "operator_session_id is required" in result["errors"]
    assert "package_id is required" in result["errors"]


def test_validate_stop_condition_rejects_invalid_contract() -> None:
    stop_condition = create_stop_condition(
        stop_condition_id="stop-1",
        operator_session_id="operator-session-1",
        package_id="package-92",
        reason="blocked",
    )
    stop_condition["contract"] = "wrong.contract"

    result = validate_stop_condition(stop_condition)

    assert result["ok"] is False
    assert "invalid contract" in result["errors"]


def test_validate_stop_condition_rejects_invalid_reason() -> None:
    stop_condition = create_stop_condition(
        stop_condition_id="stop-1",
        operator_session_id="operator-session-1",
        package_id="package-92",
        reason="paused",
    )

    result = validate_stop_condition(stop_condition)

    assert result["ok"] is False
    assert "invalid reason: paused" in result["errors"]


def test_validate_stop_condition_accepts_allowed_reasons() -> None:
    stop_condition = create_stop_condition(
        stop_condition_id="stop-1",
        operator_session_id="operator-session-1",
        package_id="package-92",
        reason="completed",
    )

    for reason in (
        "completed",
        "failed",
        "blocked",
        "waiting_for_approval",
        "validation_failed",
        "unsafe_to_continue",
        "checkpoint_missing",
        "checkpoint_invalid",
        "resume_identity_mismatch",
        "non_mainline_issue_detected",
    ):
        stop_condition["reason"] = reason
        assert validate_stop_condition(stop_condition)["ok"] is True


def test_validate_stop_condition_rejects_invalid_status() -> None:
    stop_condition = create_stop_condition(
        stop_condition_id="stop-1",
        operator_session_id="operator-session-1",
        package_id="package-92",
        reason="blocked",
    )
    stop_condition["status"] = "dismissed"

    result = validate_stop_condition(stop_condition)

    assert result["ok"] is False
    assert "invalid status: dismissed" in result["errors"]


def test_validate_stop_condition_accepts_allowed_statuses() -> None:
    stop_condition = create_stop_condition(
        stop_condition_id="stop-1",
        operator_session_id="operator-session-1",
        package_id="package-92",
        reason="blocked",
    )

    for status in ("active", "resolved"):
        stop_condition["status"] = status
        assert validate_stop_condition(stop_condition)["ok"] is True


def test_validate_stop_condition_requires_metadata_dict() -> None:
    stop_condition = create_stop_condition(
        stop_condition_id="stop-1",
        operator_session_id="operator-session-1",
        package_id="package-92",
        reason="blocked",
    )
    stop_condition["metadata"] = []

    result = validate_stop_condition(stop_condition)

    assert result["ok"] is False
    assert "metadata must be a dict" in result["errors"]


def test_stop_condition_to_summary_projects_tiny_readonly_dict_without_metadata() -> None:
    stop_condition = create_stop_condition(
        stop_condition_id="stop-1",
        operator_session_id="operator-session-1",
        package_id="package-92",
        reason="unsafe_to_continue",
        message="safety boundary reached",
        metadata={"secret": "not exposed"},
    )

    summary = stop_condition_to_summary(stop_condition)

    assert summary == {
        "stop_condition_id": "stop-1",
        "reason": "unsafe_to_continue",
        "status": "active",
        "message": "safety boundary reached",
    }
    assert "metadata" not in summary
    summary["message"] = "mutated summary"
    assert stop_condition["message"] == "safety boundary reached"


def test_stop_condition_module_avoids_forbidden_imports_and_surface_tokens() -> None:
    source = inspect.getsource(stop_condition_module)
    import_lines = [line for line in source.splitlines() if line.startswith("import ") or line.startswith("from ")]

    assert "class " not in source
    forbidden_imports = (
        "scheduler",
        "task_runner",
        "resume",
        "checkpoint_store",
        "event_log",
        "audit_reader",
        "approval",
        "issue_reporter",
        "operator_loop",
        "runtime_execution",
        "repair",
        "state_machine",
    )
    for token in forbidden_imports:
        assert all(token not in line for line in import_lines)

    forbidden_surface_tokens = (
        "scheduler",
        "task_runner",
        "event_log",
        "audit_reader",
        "issue_reporter",
        "operator_loop",
        "runtime_execution",
        "repair",
        "state_machine",
        "approve_",
        "checkpoint_store",
        "append_",
        "emit_",
        "append_",
        "save_",
        "load_",
        "open(",
        "os.",
        "pathlib",
        "time",
        "timer",
        "retry",
    )
    for token in forbidden_surface_tokens:
        assert token not in source
