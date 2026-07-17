from __future__ import annotations

import copy
import inspect

import core.runtime.aer_operator_issue_reporter as issue_module
from core.runtime.aer_operator_issue_reporter import (
    close_issue,
    create_issue,
    issue_to_summary,
    validate_issue,
)


ISSUE_CONTRACT = "aer.operator_issue_reporter.v2"


def test_create_issue_builds_open_contract() -> None:
    issue = create_issue(
        issue_id="issue-1",
        operator_session_id="operator-session-1",
        package_id="package-91",
        severity="error",
        title="Operator issue",
        description="contract-only issue",
        metadata={"source": "test"},
    )

    assert issue == {
        "contract": ISSUE_CONTRACT,
        "issue_id": "issue-1",
        "operator_session_id": "operator-session-1",
        "package_id": "package-91",
        "severity": "error",
        "status": "open",
        "title": "Operator issue",
        "description": "contract-only issue",
        "metadata": {"source": "test"},
    }
    assert validate_issue(issue)["ok"] is True


def test_create_issue_defaults_metadata_to_dict() -> None:
    issue = create_issue(
        issue_id="issue-1",
        operator_session_id="operator-session-1",
        package_id="package-91",
        severity="info",
        title="Operator issue",
    )

    assert issue["metadata"] == {}
    assert validate_issue(issue)["ok"] is True


def test_close_issue_returns_new_resolved_dict_without_mutating_input() -> None:
    issue = create_issue(
        issue_id="issue-1",
        operator_session_id="operator-session-1",
        package_id="package-91",
        severity="warning",
        title="Operator issue",
        metadata={"nested": {"value": "original"}},
    )
    original = copy.deepcopy(issue)

    closed = close_issue(issue)
    closed["metadata"]["nested"]["value"] = "mutated"

    assert closed["issue_id"] == "issue-1"
    assert closed["status"] == "resolved"
    assert issue == original
    assert validate_issue(closed)["ok"] is True


def test_validate_issue_rejects_non_dict_payload() -> None:
    result = validate_issue(None)

    assert result["ok"] is False
    assert result["contract"] == ISSUE_CONTRACT
    assert "payload must be a dict" in result["errors"]


def test_validate_issue_rejects_missing_required_fields() -> None:
    result = validate_issue({})

    assert result["ok"] is False
    for field in (
        "contract",
        "issue_id",
        "operator_session_id",
        "package_id",
        "severity",
        "status",
        "title",
        "description",
        "metadata",
    ):
        assert f"missing required field: {field}" in result["errors"]


def test_validate_issue_rejects_invalid_contract() -> None:
    issue = create_issue(
        issue_id="issue-1",
        operator_session_id="operator-session-1",
        package_id="package-91",
        severity="error",
        title="Operator issue",
    )
    issue["contract"] = "wrong.contract"

    result = validate_issue(issue)

    assert result["ok"] is False
    assert "invalid contract" in result["errors"]


def test_validate_issue_rejects_invalid_severity() -> None:
    issue = create_issue(
        issue_id="issue-1",
        operator_session_id="operator-session-1",
        package_id="package-91",
        severity="notice",
        title="Operator issue",
    )

    result = validate_issue(issue)

    assert result["ok"] is False
    assert "invalid severity: notice" in result["errors"]


def test_validate_issue_accepts_allowed_severities() -> None:
    issue = create_issue(
        issue_id="issue-1",
        operator_session_id="operator-session-1",
        package_id="package-91",
        severity="info",
        title="Operator issue",
    )

    for severity in ("info", "warning", "error", "critical"):
        issue["severity"] = severity
        assert validate_issue(issue)["ok"] is True


def test_validate_issue_rejects_invalid_status() -> None:
    issue = create_issue(
        issue_id="issue-1",
        operator_session_id="operator-session-1",
        package_id="package-91",
        severity="error",
        title="Operator issue",
    )
    issue["status"] = "closed"

    result = validate_issue(issue)

    assert result["ok"] is False
    assert "invalid status: closed" in result["errors"]


def test_validate_issue_accepts_allowed_statuses() -> None:
    issue = create_issue(
        issue_id="issue-1",
        operator_session_id="operator-session-1",
        package_id="package-91",
        severity="error",
        title="Operator issue",
    )

    for status in ("open", "resolved", "dismissed"):
        issue["status"] = status
        assert validate_issue(issue)["ok"] is True


def test_validate_issue_requires_metadata_dict() -> None:
    issue = create_issue(
        issue_id="issue-1",
        operator_session_id="operator-session-1",
        package_id="package-91",
        severity="error",
        title="Operator issue",
    )
    issue["metadata"] = []

    result = validate_issue(issue)

    assert result["ok"] is False
    assert "metadata must be a dict" in result["errors"]


def test_issue_to_summary_projects_tiny_readonly_dict_without_metadata() -> None:
    issue = create_issue(
        issue_id="issue-1",
        operator_session_id="operator-session-1",
        package_id="package-91",
        severity="critical",
        title="Operator issue",
        description="not part of summary",
        metadata={"secret": "not exposed"},
    )

    summary = issue_to_summary(issue)

    assert summary == {
        "issue_id": "issue-1",
        "severity": "critical",
        "status": "open",
        "title": "Operator issue",
    }
    assert "metadata" not in summary
    assert "description" not in summary
    summary["title"] = "mutated summary"
    assert issue["title"] == "Operator issue"


def test_issue_reporter_module_avoids_forbidden_imports_and_surface_tokens() -> None:
    source = inspect.getsource(issue_module)

    assert "class " not in source
    forbidden = (
        "scheduler",
        "task_runner",
        "resume",
        "checkpoint_store",
        "event_log",
        "audit_reader",
        "approval",
        "operator_loop",
        "runtime_execution",
        "repair",
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
    for token in forbidden:
        assert token not in source
