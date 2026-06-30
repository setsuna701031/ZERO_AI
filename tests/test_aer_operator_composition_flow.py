from __future__ import annotations

import copy
import inspect

import core.runtime.aer_operator_composition_flow as composition_flow_module
from core.runtime.aer_operator_composition_flow import (
    compose_operator_flow,
    operator_flow_to_summary,
)
from core.runtime.aer_operator_decision import create_decision
from core.runtime.aer_operator_plan import create_plan


def make_decision(decision_type: str = "continue") -> dict:
    return create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-96",
        decision_type=decision_type,
        decision_reason="operator composition flow test",
        created_at="2026-06-30T00:00:00Z",
        metadata={"nested": {"value": "original"}},
    )


def make_plan(plan_type: str = "continue") -> dict:
    return create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-96",
        plan_type=plan_type,
        plan_reason="operator composition flow test",
        created_at="2026-06-30T00:00:00Z",
        steps=[{"nested": {"value": "original"}}],
        metadata={"nested": {"value": "original"}},
    )


def test_compose_operator_flow_continue_path() -> None:
    result = compose_operator_flow(make_decision("continue"), make_plan("continue"))

    assert result == {
        "outcome": "continue",
        "decision": {
            "outcome": "continue",
            "decision_id": "decision-1",
            "decision_type": "continue",
            "status": "proposed",
        },
        "plan": {
            "outcome": "continue",
            "plan_id": "plan-1",
            "plan_type": "continue",
            "status": "proposed",
        },
    }


def test_compose_operator_flow_approval_precedence() -> None:
    result = compose_operator_flow(
        make_decision("continue"),
        make_plan("request_approval"),
    )

    assert result["outcome"] == "approval_required"
    assert result["decision"]["outcome"] == "continue"
    assert result["plan"]["outcome"] == "approval_required"


def test_compose_operator_flow_stop_precedence() -> None:
    result = compose_operator_flow(make_decision("stop"), make_plan("request_approval"))

    assert result["outcome"] == "stopped"
    assert result["decision"]["outcome"] == "stopped"
    assert result["plan"]["outcome"] == "approval_required"


def test_compose_operator_flow_issue_precedence() -> None:
    result = compose_operator_flow(make_decision("report_issue"), make_plan("stop"))

    assert result["outcome"] == "issue_reported"
    assert result["decision"]["outcome"] == "issue_reported"
    assert result["plan"]["outcome"] == "stopped"


def test_compose_operator_flow_invalid_decision_reports_issue() -> None:
    decision = make_decision("continue")
    decision["status"] = "running"

    result = compose_operator_flow(decision, make_plan("continue"))

    assert result["outcome"] == "issue_reported"
    assert result["decision"] == {
        "outcome": "issue_reported",
        "decision_id": "decision-1",
        "decision_type": "continue",
        "status": "running",
    }
    assert result["plan"]["outcome"] == "continue"


def test_compose_operator_flow_invalid_plan_reports_issue() -> None:
    plan = make_plan("continue")
    plan["status"] = "running"

    result = compose_operator_flow(make_decision("continue"), plan)

    assert result["outcome"] == "issue_reported"
    assert result["decision"]["outcome"] == "continue"
    assert result["plan"] == {
        "outcome": "issue_reported",
        "plan_id": "plan-1",
        "plan_type": "continue",
        "status": "running",
    }


def test_compose_operator_flow_valid_non_flow_owned_type_reports_issue() -> None:
    result = compose_operator_flow(make_decision("resume"), make_plan("checkpoint"))

    assert result["outcome"] == "issue_reported"
    assert result["decision"]["outcome"] == "issue_reported"
    assert result["plan"]["outcome"] == "issue_reported"


def test_operator_flow_to_summary_returns_only_public_fields() -> None:
    flow = {
        "outcome": "continue",
        "decision": {
            "outcome": "continue",
            "decision_id": "decision-1",
            "decision_type": "continue",
            "status": "proposed",
            "metadata": {"secret": "not exposed"},
        },
        "plan": {
            "outcome": "continue",
            "plan_id": "plan-1",
            "plan_type": "continue",
            "status": "proposed",
            "metadata": {"secret": "not exposed"},
        },
        "metadata": {"secret": "not exposed"},
    }

    summary = operator_flow_to_summary(flow)

    assert summary == {
        "outcome": "continue",
        "decision": {
            "outcome": "continue",
            "decision_id": "decision-1",
            "decision_type": "continue",
            "status": "proposed",
        },
        "plan": {
            "outcome": "continue",
            "plan_id": "plan-1",
            "plan_type": "continue",
            "status": "proposed",
        },
    }
    assert "metadata" not in summary
    assert "metadata" not in summary["decision"]
    assert "metadata" not in summary["plan"]


def test_composition_flow_returns_new_immutable_outputs_without_mutating_inputs() -> None:
    decision = make_decision("continue")
    plan = make_plan("continue")
    original_decision = copy.deepcopy(decision)
    original_plan = copy.deepcopy(plan)

    result = compose_operator_flow(decision, plan)
    summary = operator_flow_to_summary(result)
    result["decision"]["decision_id"] = "mutated"
    result["plan"]["plan_id"] = "mutated"
    summary["decision"]["status"] = "mutated"
    summary["plan"]["status"] = "mutated"

    assert decision == original_decision
    assert plan == original_plan
    assert result is not decision
    assert result is not plan
    assert summary is not result
    assert decision["decision_id"] == "decision-1"
    assert plan["plan_id"] == "plan-1"


def test_composition_flow_exposes_only_public_api() -> None:
    assert composition_flow_module.__all__ == [
        "compose_operator_flow",
        "operator_flow_to_summary",
    ]


def test_composition_flow_uses_only_flow_functions() -> None:
    source = inspect.getsource(composition_flow_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    assert "evaluate_decision" in source
    assert "decision_flow_summary" in source
    assert "evaluate_plan" in source
    assert "plan_flow_summary" in source
    assert all("validate_" not in line for line in import_lines)
    assert all("create_" not in line for line in import_lines)
    assert all("accept_" not in line for line in import_lines)


def test_composition_flow_avoids_forbidden_imports() -> None:
    source = inspect.getsource(composition_flow_module)
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
        "persistent_operator",
    )
    for token in forbidden_imports:
        assert all(token not in line for line in import_lines)


def test_composition_flow_has_no_runtime_coupling() -> None:
    source = inspect.getsource(composition_flow_module)
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
        "checkpoint",
        "resume",
        "while ",
        "for ",
    )
    for token in forbidden_surface_tokens:
        assert token not in surface


def test_composition_flow_has_no_scheduler_coupling() -> None:
    source = inspect.getsource(composition_flow_module)

    forbidden_surface_tokens = (
        "scheduler",
        "schedule",
        "task_runner",
        "TaskRunner",
        "enqueue",
        "queue",
        "worker",
        "loop",
    )
    for token in forbidden_surface_tokens:
        assert token not in source
