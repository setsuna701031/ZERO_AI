from __future__ import annotations

import copy
import inspect

import core.runtime.aer_operator_plan as plan_module
from core.runtime.aer_operator_plan import (
    accept_plan,
    create_plan,
    plan_to_summary,
    validate_plan,
)


PLAN_CONTRACT = "aer.operator_plan.v2"


def test_create_plan_builds_proposed_contract() -> None:
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-95",
        plan_type="continue",
        plan_reason="all contract checks passed",
        created_at="2026-06-30T00:00:00Z",
        steps=[{"step_id": "step-1"}],
        metadata={"source": "test"},
    )

    assert plan == {
        "contract": PLAN_CONTRACT,
        "plan_id": "plan-1",
        "operator_session_id": "operator-session-1",
        "package_id": "package-95",
        "plan_type": "continue",
        "plan_reason": "all contract checks passed",
        "status": "proposed",
        "steps": [{"step_id": "step-1"}],
        "metadata": {"source": "test"},
        "created_at": "2026-06-30T00:00:00Z",
    }
    assert validate_plan(plan)["ok"] is True


def test_create_plan_defaults_collections_to_fresh_values() -> None:
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-95",
        plan_type="stop",
        plan_reason="stop condition proposed",
    )

    assert plan["steps"] == []
    assert plan["metadata"] == {}
    assert validate_plan(plan)["ok"] is True


def test_accept_plan_returns_new_accepted_dict_without_mutating_input() -> None:
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-95",
        plan_type="request_approval",
        plan_reason="human approval needed",
        steps=[{"nested": {"value": "original"}}],
        metadata={"nested": {"value": "original"}},
    )
    original = copy.deepcopy(plan)

    accepted = accept_plan(plan, accepted_by="human-1")
    accepted["steps"][0]["nested"]["value"] = "mutated"
    accepted["metadata"]["nested"]["value"] = "mutated"

    assert accepted["plan_id"] == "plan-1"
    assert accepted["status"] == "accepted"
    assert accepted["accepted_by"] == "human-1"
    assert plan == original
    assert validate_plan(accepted)["ok"] is True


def test_validate_plan_rejects_non_dict_payload() -> None:
    result = validate_plan(None)

    assert result["ok"] is False
    assert result["contract"] == PLAN_CONTRACT
    assert "payload must be a dict" in result["errors"]


def test_validate_plan_rejects_missing_required_fields() -> None:
    result = validate_plan({})

    assert result["ok"] is False
    for field in (
        "contract",
        "plan_id",
        "operator_session_id",
        "package_id",
        "plan_type",
        "plan_reason",
        "status",
        "steps",
        "metadata",
        "created_at",
    ):
        assert f"missing required field: {field}" in result["errors"]


def test_validate_plan_rejects_empty_identity_and_reason_fields() -> None:
    plan = create_plan(
        plan_id="",
        operator_session_id="",
        package_id="",
        plan_type="continue",
        plan_reason="",
    )

    result = validate_plan(plan)

    assert result["ok"] is False
    assert "plan_id is required" in result["errors"]
    assert "operator_session_id is required" in result["errors"]
    assert "package_id is required" in result["errors"]
    assert "plan_reason is required" in result["errors"]


def test_validate_plan_rejects_invalid_contract() -> None:
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-95",
        plan_type="continue",
        plan_reason="all contract checks passed",
    )
    plan["contract"] = "wrong.contract"

    result = validate_plan(plan)

    assert result["ok"] is False
    assert "invalid contract" in result["errors"]


def test_validate_plan_rejects_invalid_plan_type() -> None:
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-95",
        plan_type="dispatch",
        plan_reason="not allowed",
    )

    result = validate_plan(plan)

    assert result["ok"] is False
    assert "invalid plan_type: dispatch" in result["errors"]


def test_validate_plan_accepts_allowed_plan_types() -> None:
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-95",
        plan_type="continue",
        plan_reason="allowed plan type",
    )

    for plan_type in (
        "continue",
        "stop",
        "request_approval",
        "report_issue",
        "checkpoint",
        "resume",
    ):
        plan["plan_type"] = plan_type
        assert validate_plan(plan)["ok"] is True


def test_validate_plan_rejects_invalid_status() -> None:
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-95",
        plan_type="continue",
        plan_reason="all contract checks passed",
    )
    plan["status"] = "active"

    result = validate_plan(plan)

    assert result["ok"] is False
    assert "invalid status: active" in result["errors"]


def test_validate_plan_accepts_allowed_statuses() -> None:
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-95",
        plan_type="continue",
        plan_reason="all contract checks passed",
    )

    for status in ("proposed", "accepted", "rejected"):
        plan["status"] = status
        assert validate_plan(plan)["ok"] is True


def test_validate_plan_requires_steps_list_and_metadata_dict() -> None:
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-95",
        plan_type="continue",
        plan_reason="all contract checks passed",
    )
    plan["steps"] = {}
    plan["metadata"] = []

    result = validate_plan(plan)

    assert result["ok"] is False
    assert "steps must be a list" in result["errors"]
    assert "metadata must be a dict" in result["errors"]


def test_plan_to_summary_projects_tiny_readonly_dict_without_collections() -> None:
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-95",
        plan_type="checkpoint",
        plan_reason="checkpoint plan proposed",
        steps=[{"secret": "not exposed"}],
        metadata={"secret": "not exposed"},
    )

    summary = plan_to_summary(plan)

    assert summary == {
        "plan_id": "plan-1",
        "plan_type": "checkpoint",
        "status": "proposed",
        "plan_reason": "checkpoint plan proposed",
    }
    assert "metadata" not in summary
    assert "steps" not in summary
    summary["plan_reason"] = "mutated summary"
    assert plan["plan_reason"] == "checkpoint plan proposed"


def test_plan_module_avoids_forbidden_imports_and_surface_tokens() -> None:
    source = inspect.getsource(plan_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

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
