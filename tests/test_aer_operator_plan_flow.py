from __future__ import annotations

import copy
import inspect

import core.runtime.aer_operator_plan_flow as plan_flow_module
from core.runtime.aer_operator_plan import create_plan
from core.runtime.aer_operator_plan_flow import evaluate_plan, plan_flow_summary


def make_plan(plan_type: str = "continue") -> dict:
    return create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-95",
        plan_type=plan_type,
        plan_reason="operator plan flow test",
        created_at="2026-06-30T00:00:00Z",
        steps=[{"nested": {"value": "original"}}],
        metadata={"nested": {"value": "original"}},
    )


def test_evaluate_plan_continue_path() -> None:
    result = evaluate_plan(make_plan("continue"))

    assert result == {
        "outcome": "continue",
        "plan_id": "plan-1",
        "plan_type": "continue",
        "status": "proposed",
    }


def test_evaluate_plan_approval_path() -> None:
    result = evaluate_plan(make_plan("request_approval"))

    assert result["outcome"] == "approval_required"
    assert result["plan_type"] == "request_approval"


def test_evaluate_plan_issue_path() -> None:
    result = evaluate_plan(make_plan("report_issue"))

    assert result["outcome"] == "issue_reported"
    assert result["plan_type"] == "report_issue"


def test_evaluate_plan_stop_path() -> None:
    result = evaluate_plan(make_plan("stop"))

    assert result["outcome"] == "stopped"
    assert result["plan_type"] == "stop"


def test_evaluate_plan_invalid_plan_reports_issue() -> None:
    plan = make_plan("continue")
    plan["status"] = "running"

    result = evaluate_plan(plan)

    assert result == {
        "outcome": "issue_reported",
        "plan_id": "plan-1",
        "plan_type": "continue",
        "status": "running",
    }


def test_evaluate_plan_reports_valid_non_flow_plan_types_as_issues() -> None:
    result = evaluate_plan(make_plan("checkpoint"))

    assert result["outcome"] == "issue_reported"
    assert result["plan_type"] == "checkpoint"


def test_plan_flow_summary_returns_only_public_fields() -> None:
    flow = {
        "outcome": "continue",
        "plan_id": "plan-1",
        "plan_type": "continue",
        "status": "proposed",
        "metadata": {"secret": "not exposed"},
    }

    summary = plan_flow_summary(flow)

    assert summary == {
        "outcome": "continue",
        "plan_id": "plan-1",
        "plan_type": "continue",
        "status": "proposed",
    }
    assert "metadata" not in summary


def test_plan_flow_returns_new_immutable_outputs_without_mutating_input() -> None:
    plan = make_plan("continue")
    original = copy.deepcopy(plan)

    result = evaluate_plan(plan)
    summary = plan_flow_summary(result)
    result["plan_id"] = "mutated"
    summary["status"] = "mutated"

    assert plan == original
    assert result is not plan
    assert summary is not result
    assert plan["plan_id"] == "plan-1"
    assert plan["status"] == "proposed"


def test_plan_flow_exposes_only_public_api() -> None:
    assert plan_flow_module.__all__ == ["evaluate_plan", "plan_flow_summary"]


def test_plan_flow_uses_only_plan_contract_validator() -> None:
    source = inspect.getsource(plan_flow_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    assert "validate_plan" in source
    assert all(" create_" not in line for line in import_lines)
    assert all(" accept_" not in line for line in import_lines)


def test_plan_flow_avoids_forbidden_imports() -> None:
    source = inspect.getsource(plan_flow_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    forbidden_imports = (
        "scheduler",
        "task_runner",
        "operator_loop",
        "event_log",
        "checkpoint_store",
        "resume",
        "audit_reader",
    )
    for token in forbidden_imports:
        assert all(token not in line for line in import_lines)


def test_plan_flow_has_no_runtime_coupling() -> None:
    source = inspect.getsource(plan_flow_module)
    surface = "\n".join(
        line
        for line in source.splitlines()
        if not line.startswith("import ") and not line.startswith("from ")
    )

    forbidden_surface_tokens = (
        "run_",
        "execute",
        "dispatch",
        "task_runtime",
        "runtime_execution",
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
        "repair",
        "while ",
        "for ",
    )
    for token in forbidden_surface_tokens:
        assert token not in surface


def test_plan_flow_has_no_scheduler_coupling() -> None:
    source = inspect.getsource(plan_flow_module)

    forbidden_surface_tokens = (
        "scheduler",
        "schedule",
        "task_runner",
        "TaskRunner",
        "enqueue",
        "queue",
        "worker",
    )
    for token in forbidden_surface_tokens:
        assert token not in source
