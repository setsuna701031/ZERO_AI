from __future__ import annotations

import copy
import inspect

import core.runtime.aer_operator_approval as approval_module
from core.runtime.aer_operator_approval import (
    AER_OPERATOR_APPROVAL_CONTRACT,
    approve_request,
    create_approval_request,
    reject_request,
    validate_approval,
)


def test_create_approval_request_builds_pending_contract() -> None:
    approval = create_approval_request(
        approval_id="approval-1",
        operator_session_id="operator-session-1",
        package_id="package-90",
        requested_action="continue_operator",
        request_reason="human boundary required",
        metadata={"source": "test"},
    )

    assert approval == {
        "contract": AER_OPERATOR_APPROVAL_CONTRACT,
        "approval_id": "approval-1",
        "operator_session_id": "operator-session-1",
        "package_id": "package-90",
        "requested_action": "continue_operator",
        "request_reason": "human boundary required",
        "status": "pending",
        "metadata": {"source": "test"},
    }
    assert validate_approval(approval)["ok"] is True


def test_create_approval_request_defaults_metadata_to_dict() -> None:
    approval = create_approval_request(
        approval_id="approval-1",
        operator_session_id="operator-session-1",
        package_id="package-90",
        requested_action="continue_operator",
    )

    assert approval["metadata"] == {}
    assert validate_approval(approval)["ok"] is True


def test_approve_request_returns_new_approved_dict_without_mutating_input() -> None:
    approval = create_approval_request(
        approval_id="approval-1",
        operator_session_id="operator-session-1",
        package_id="package-90",
        requested_action="continue_operator",
        metadata={"nested": {"value": "original"}},
    )
    original = copy.deepcopy(approval)

    approved = approve_request(approval, approved_by="human-1")
    approved["metadata"]["nested"]["value"] = "mutated"

    assert approved["approval_id"] == "approval-1"
    assert approved["status"] == "approved"
    assert approved["approved_by"] == "human-1"
    assert approval == original
    assert validate_approval(approved)["ok"] is True


def test_reject_request_returns_new_rejected_dict_without_mutating_input() -> None:
    approval = create_approval_request(
        approval_id="approval-1",
        operator_session_id="operator-session-1",
        package_id="package-90",
        requested_action="continue_operator",
        metadata={"nested": {"value": "original"}},
    )
    original = copy.deepcopy(approval)

    rejected = reject_request(
        approval,
        rejected_by="human-1",
        rejection_reason="not enough evidence",
    )
    rejected["metadata"]["nested"]["value"] = "mutated"

    assert rejected["approval_id"] == "approval-1"
    assert rejected["status"] == "rejected"
    assert rejected["rejected_by"] == "human-1"
    assert rejected["rejection_reason"] == "not enough evidence"
    assert approval == original
    assert validate_approval(rejected)["ok"] is True


def test_approval_id_is_immutable_across_approve_and_reject() -> None:
    approval = create_approval_request(
        approval_id="approval-immutable",
        operator_session_id="operator-session-1",
        package_id="package-90",
        requested_action="continue_operator",
    )

    assert approve_request(approval)["approval_id"] == "approval-immutable"
    assert reject_request(approval)["approval_id"] == "approval-immutable"


def test_validate_approval_rejects_invalid_schema() -> None:
    result = validate_approval(None)

    assert result["ok"] is False
    assert result["contract"] == AER_OPERATOR_APPROVAL_CONTRACT
    assert "payload must be a dict" in result["errors"]


def test_validate_approval_rejects_missing_required_fields() -> None:
    result = validate_approval({})

    assert result["ok"] is False
    for field in (
        "contract",
        "approval_id",
        "operator_session_id",
        "package_id",
        "requested_action",
        "request_reason",
        "status",
        "metadata",
    ):
        assert f"missing required field: {field}" in result["errors"]


def test_validate_approval_rejects_empty_identity_and_action_fields() -> None:
    approval = create_approval_request(
        approval_id="",
        operator_session_id="",
        package_id="",
        requested_action="",
    )

    result = validate_approval(approval)

    assert result["ok"] is False
    assert "approval_id is required" in result["errors"]
    assert "operator_session_id is required" in result["errors"]
    assert "package_id is required" in result["errors"]
    assert "requested_action is required" in result["errors"]


def test_validate_approval_rejects_invalid_contract_and_status() -> None:
    approval = create_approval_request(
        approval_id="approval-1",
        operator_session_id="operator-session-1",
        package_id="package-90",
        requested_action="continue_operator",
    )
    approval["contract"] = "wrong.contract"
    approval["status"] = "waiting"

    result = validate_approval(approval)

    assert result["ok"] is False
    assert "invalid contract" in result["errors"]
    assert "invalid status: waiting" in result["errors"]


def test_validate_approval_accepts_allowed_statuses() -> None:
    approval = create_approval_request(
        approval_id="approval-1",
        operator_session_id="operator-session-1",
        package_id="package-90",
        requested_action="continue_operator",
    )

    for status in ("pending", "approved", "rejected", "expired"):
        approval["status"] = status
        assert validate_approval(approval)["ok"] is True


def test_validate_approval_requires_metadata_dict() -> None:
    approval = create_approval_request(
        approval_id="approval-1",
        operator_session_id="operator-session-1",
        package_id="package-90",
        requested_action="continue_operator",
    )
    approval["metadata"] = []

    result = validate_approval(approval)

    assert result["ok"] is False
    assert "metadata must be a dict" in result["errors"]


def test_approval_module_avoids_forbidden_imports_and_surface_tokens() -> None:
    source = inspect.getsource(approval_module)

    assert "class " not in source
    forbidden = (
        "scheduler",
        "task_runner",
        "resume",
        "checkpoint",
        "event_log",
        "audit_reader",
        "operator_loop",
        "runtime execution",
        "append_operator_event",
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
