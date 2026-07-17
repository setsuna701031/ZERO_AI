from __future__ import annotations

import copy
import inspect

import core.runtime.aer_operator_decision as decision_module
from core.runtime.aer_operator_decision import (
    accept_decision,
    create_decision,
    decision_to_summary,
    validate_decision,
)


DECISION_CONTRACT = "aer.operator_decision.v2"


def test_create_decision_builds_proposed_contract() -> None:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-93",
        decision_type="continue",
        decision_reason="all contract checks passed",
        created_at="2026-06-30T00:00:00Z",
        metadata={"source": "test"},
    )

    assert decision == {
        "contract": DECISION_CONTRACT,
        "decision_id": "decision-1",
        "operator_session_id": "operator-session-1",
        "package_id": "package-93",
        "decision_type": "continue",
        "decision_reason": "all contract checks passed",
        "status": "proposed",
        "metadata": {"source": "test"},
        "created_at": "2026-06-30T00:00:00Z",
    }
    assert validate_decision(decision)["ok"] is True


def test_create_decision_defaults_metadata_to_dict() -> None:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-93",
        decision_type="stop",
        decision_reason="stop condition proposed",
    )

    assert decision["metadata"] == {}
    assert validate_decision(decision)["ok"] is True


def test_accept_decision_returns_new_accepted_dict_without_mutating_input() -> None:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-93",
        decision_type="request_approval",
        decision_reason="human approval needed",
        metadata={"nested": {"value": "original"}},
    )
    original = copy.deepcopy(decision)

    accepted = accept_decision(decision, accepted_by="human-1")
    accepted["metadata"]["nested"]["value"] = "mutated"

    assert accepted["decision_id"] == "decision-1"
    assert accepted["status"] == "accepted"
    assert accepted["accepted_by"] == "human-1"
    assert decision == original
    assert validate_decision(accepted)["ok"] is True


def test_decision_id_is_preserved_when_accepted() -> None:
    decision = create_decision(
        decision_id="decision-immutable",
        operator_session_id="operator-session-1",
        package_id="package-93",
        decision_type="report_issue",
        decision_reason="issue report proposed",
    )

    accepted = accept_decision(decision)

    assert accepted["decision_id"] == "decision-immutable"


def test_validate_decision_rejects_non_dict_payload() -> None:
    result = validate_decision(None)

    assert result["ok"] is False
    assert result["contract"] == DECISION_CONTRACT
    assert "payload must be a dict" in result["errors"]


def test_validate_decision_rejects_missing_required_fields() -> None:
    result = validate_decision({})

    assert result["ok"] is False
    for field in (
        "contract",
        "decision_id",
        "operator_session_id",
        "package_id",
        "decision_type",
        "decision_reason",
        "status",
        "metadata",
        "created_at",
    ):
        assert f"missing required field: {field}" in result["errors"]


def test_validate_decision_rejects_empty_identity_and_reason_fields() -> None:
    decision = create_decision(
        decision_id="",
        operator_session_id="",
        package_id="",
        decision_type="continue",
        decision_reason="",
    )

    result = validate_decision(decision)

    assert result["ok"] is False
    assert "decision_id is required" in result["errors"]
    assert "operator_session_id is required" in result["errors"]
    assert "package_id is required" in result["errors"]
    assert "decision_reason is required" in result["errors"]


def test_validate_decision_rejects_invalid_contract() -> None:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-93",
        decision_type="continue",
        decision_reason="all contract checks passed",
    )
    decision["contract"] = "wrong.contract"

    result = validate_decision(decision)

    assert result["ok"] is False
    assert "invalid contract" in result["errors"]


def test_validate_decision_rejects_invalid_decision_type() -> None:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-93",
        decision_type="dispatch",
        decision_reason="not allowed",
    )

    result = validate_decision(decision)

    assert result["ok"] is False
    assert "invalid decision_type: dispatch" in result["errors"]


def test_validate_decision_accepts_allowed_decision_types() -> None:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-93",
        decision_type="continue",
        decision_reason="allowed decision type",
    )

    for decision_type in (
        "continue",
        "stop",
        "request_approval",
        "report_issue",
        "checkpoint",
        "resume",
    ):
        decision["decision_type"] = decision_type
        assert validate_decision(decision)["ok"] is True


def test_validate_decision_rejects_invalid_status() -> None:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-93",
        decision_type="continue",
        decision_reason="all contract checks passed",
    )
    decision["status"] = "active"

    result = validate_decision(decision)

    assert result["ok"] is False
    assert "invalid status: active" in result["errors"]


def test_validate_decision_accepts_allowed_statuses() -> None:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-93",
        decision_type="continue",
        decision_reason="all contract checks passed",
    )

    for status in ("proposed", "accepted", "rejected"):
        decision["status"] = status
        assert validate_decision(decision)["ok"] is True


def test_validate_decision_requires_metadata_dict() -> None:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-93",
        decision_type="continue",
        decision_reason="all contract checks passed",
    )
    decision["metadata"] = []

    result = validate_decision(decision)

    assert result["ok"] is False
    assert "metadata must be a dict" in result["errors"]


def test_decision_to_summary_projects_tiny_readonly_dict_without_metadata() -> None:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-93",
        decision_type="checkpoint",
        decision_reason="checkpoint decision proposed",
        metadata={"secret": "not exposed"},
    )

    summary = decision_to_summary(decision)

    assert summary == {
        "decision_id": "decision-1",
        "decision_type": "checkpoint",
        "status": "proposed",
        "decision_reason": "checkpoint decision proposed",
    }
    assert "metadata" not in summary
    assert "created_at" not in summary
    summary["decision_reason"] = "mutated summary"
    assert decision["decision_reason"] == "checkpoint decision proposed"


def test_decision_module_avoids_forbidden_imports_and_surface_tokens() -> None:
    source = inspect.getsource(decision_module)
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
        "stop_condition",
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
        "checkpoint_store",
        "event_log",
        "audit_reader",
        "issue_reporter",
        "stop_condition",
        "operator_loop",
        "runtime_execution",
        "repair",
        "state_machine",
        "approve_",
        "append_",
        "emit_",
        "save_",
        "load_",
        "open(",
        "os.",
        "pathlib",
        "time",
        "timer",
        "retry",
        "dispatch",
    )
    for token in forbidden_surface_tokens:
        assert token not in source
