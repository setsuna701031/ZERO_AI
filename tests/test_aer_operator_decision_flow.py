from __future__ import annotations

import copy
import inspect

import core.runtime.aer_operator_decision_flow as decision_flow_module
from core.runtime.aer_operator_decision import create_decision
from core.runtime.aer_operator_decision_flow import (
    decision_flow_summary,
    evaluate_decision,
)


def make_decision(decision_type: str = "continue") -> dict:
    return create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-94",
        decision_type=decision_type,
        decision_reason="operator decision flow test",
        created_at="2026-06-30T00:00:00Z",
        metadata={"nested": {"value": "original"}},
    )


def test_evaluate_decision_continue_path() -> None:
    result = evaluate_decision(make_decision("continue"))

    assert result == {
        "outcome": "continue",
        "decision_id": "decision-1",
        "decision_type": "continue",
        "status": "proposed",
    }


def test_evaluate_decision_approval_path() -> None:
    result = evaluate_decision(make_decision("request_approval"))

    assert result["outcome"] == "approval_required"
    assert result["decision_type"] == "request_approval"


def test_evaluate_decision_issue_path() -> None:
    result = evaluate_decision(make_decision("report_issue"))

    assert result["outcome"] == "issue_reported"
    assert result["decision_type"] == "report_issue"


def test_evaluate_decision_stop_path() -> None:
    result = evaluate_decision(make_decision("stop"))

    assert result["outcome"] == "stopped"
    assert result["decision_type"] == "stop"


def test_evaluate_decision_invalid_decision_reports_issue() -> None:
    decision = make_decision("continue")
    decision["status"] = "running"

    result = evaluate_decision(decision)

    assert result == {
        "outcome": "issue_reported",
        "decision_id": "decision-1",
        "decision_type": "continue",
        "status": "running",
    }


def test_evaluate_decision_reports_valid_non_flow_decision_types_as_issues() -> None:
    result = evaluate_decision(make_decision("checkpoint"))

    assert result["outcome"] == "issue_reported"
    assert result["decision_type"] == "checkpoint"


def test_decision_flow_summary_returns_only_public_fields() -> None:
    flow = {
        "outcome": "continue",
        "decision_id": "decision-1",
        "decision_type": "continue",
        "status": "proposed",
        "metadata": {"secret": "not exposed"},
    }

    summary = decision_flow_summary(flow)

    assert summary == {
        "outcome": "continue",
        "decision_id": "decision-1",
        "decision_type": "continue",
        "status": "proposed",
    }
    assert "metadata" not in summary


def test_decision_flow_returns_new_immutable_outputs_without_mutating_input() -> None:
    decision = make_decision("continue")
    original = copy.deepcopy(decision)

    result = evaluate_decision(decision)
    summary = decision_flow_summary(result)
    result["decision_id"] = "mutated"
    summary["status"] = "mutated"

    assert decision == original
    assert result is not decision
    assert summary is not result
    assert decision["decision_id"] == "decision-1"
    assert decision["status"] == "proposed"


def test_decision_flow_exposes_only_public_api() -> None:
    assert decision_flow_module.__all__ == ["evaluate_decision", "decision_flow_summary"]


def test_decision_flow_uses_only_allowed_contract_validators() -> None:
    source = inspect.getsource(decision_flow_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    assert "validate_decision" in source
    assert "validate_approval" in source
    assert "validate_issue" in source
    assert "validate_stop_condition" in source
    assert all(" create_" not in line for line in import_lines)
    assert all(" approve_" not in line for line in import_lines)
    assert all(" reject_" not in line for line in import_lines)
    assert all(" close_" not in line for line in import_lines)
    assert all(" resolve_" not in line for line in import_lines)


def test_decision_flow_avoids_forbidden_imports() -> None:
    source = inspect.getsource(decision_flow_module)
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


def test_decision_flow_has_no_runtime_coupling() -> None:
    source = inspect.getsource(decision_flow_module)
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


def test_decision_flow_has_no_scheduler_coupling() -> None:
    source = inspect.getsource(decision_flow_module)

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
