from __future__ import annotations

import copy
import inspect

import core.runtime.aer_operator_state as state_module
from core.runtime.aer_operator_composition_flow import compose_operator_flow
from core.runtime.aer_operator_decision import create_decision
from core.runtime.aer_operator_plan import create_plan
from core.runtime.aer_operator_state import (
    create_operator_state,
    operator_state_to_summary,
    validate_operator_state,
)


STATE_CONTRACT = "aer.operator_state.v2"


def make_composition_summary(decision_type: str = "continue", plan_type: str = "continue") -> dict:
    decision = create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-97",
        decision_type=decision_type,
        decision_reason="operator state test",
        created_at="2026-06-30T00:00:00Z",
        metadata={"nested": {"value": "original"}},
    )
    plan = create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-97",
        plan_type=plan_type,
        plan_reason="operator state test",
        created_at="2026-06-30T00:00:00Z",
        steps=[{"nested": {"value": "original"}}],
        metadata={"nested": {"value": "original"}},
    )
    return compose_operator_flow(decision, plan)


def test_create_operator_state_wraps_composition_summary() -> None:
    composition_summary = make_composition_summary()

    operator_state = create_operator_state(composition_summary=composition_summary)

    assert operator_state == {
        "contract": STATE_CONTRACT,
        "outcome": "continue",
        "composition_summary": {
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
        },
    }
    assert validate_operator_state(operator_state)["ok"] is True


def test_create_operator_state_preserves_composition_outcome() -> None:
    approval_state = create_operator_state(
        composition_summary=make_composition_summary("continue", "request_approval")
    )
    stopped_state = create_operator_state(
        composition_summary=make_composition_summary("stop", "request_approval")
    )
    issue_state = create_operator_state(
        composition_summary=make_composition_summary("report_issue", "stop")
    )

    assert approval_state["outcome"] == "approval_required"
    assert stopped_state["outcome"] == "stopped"
    assert issue_state["outcome"] == "issue_reported"
    assert validate_operator_state(approval_state)["ok"] is True
    assert validate_operator_state(stopped_state)["ok"] is True
    assert validate_operator_state(issue_state)["ok"] is True


def test_operator_state_normalizes_input_to_public_composition_summary() -> None:
    composition_summary = make_composition_summary()
    composition_summary["metadata"] = {"secret": "not exposed"}
    composition_summary["decision"]["metadata"] = {"secret": "not exposed"}
    composition_summary["plan"]["metadata"] = {"secret": "not exposed"}

    operator_state = create_operator_state(composition_summary=composition_summary)

    assert "metadata" not in operator_state["composition_summary"]
    assert "metadata" not in operator_state["composition_summary"]["decision"]
    assert "metadata" not in operator_state["composition_summary"]["plan"]
    assert validate_operator_state(operator_state)["ok"] is True


def test_create_operator_state_returns_new_outputs_without_mutating_input() -> None:
    composition_summary = make_composition_summary()
    original = copy.deepcopy(composition_summary)

    operator_state = create_operator_state(composition_summary=composition_summary)
    summary = operator_state_to_summary(operator_state)
    operator_state["composition_summary"]["decision"]["decision_id"] = "mutated"
    summary["composition_summary"]["plan"]["plan_id"] = "mutated"

    assert composition_summary == original
    assert operator_state is not composition_summary
    assert summary is not operator_state
    assert composition_summary["decision"]["decision_id"] == "decision-1"
    assert composition_summary["plan"]["plan_id"] == "plan-1"


def test_operator_state_to_summary_returns_public_fields_only() -> None:
    operator_state = create_operator_state(composition_summary=make_composition_summary())
    operator_state["private"] = {"secret": "not exposed"}
    operator_state["composition_summary"]["private"] = {"secret": "not exposed"}

    summary = operator_state_to_summary(operator_state)

    assert summary == {
        "outcome": "continue",
        "composition_summary": {
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
        },
    }
    assert "private" not in summary
    assert "private" not in summary["composition_summary"]


def test_validate_operator_state_rejects_non_dict_payload() -> None:
    result = validate_operator_state(None)

    assert result["ok"] is False
    assert result["contract"] == STATE_CONTRACT
    assert "payload must be a dict" in result["errors"]


def test_validate_operator_state_rejects_missing_required_fields() -> None:
    result = validate_operator_state({})

    assert result["ok"] is False
    assert "missing required field: contract" in result["errors"]
    assert "missing required field: outcome" in result["errors"]
    assert "missing required field: composition_summary" in result["errors"]


def test_validate_operator_state_rejects_invalid_contract() -> None:
    operator_state = create_operator_state(composition_summary=make_composition_summary())
    operator_state["contract"] = "wrong.contract"

    result = validate_operator_state(operator_state)

    assert result["ok"] is False
    assert "invalid contract" in result["errors"]


def test_validate_operator_state_rejects_invalid_outcome() -> None:
    operator_state = create_operator_state(composition_summary=make_composition_summary())
    operator_state["outcome"] = "queued"

    result = validate_operator_state(operator_state)

    assert result["ok"] is False
    assert "invalid outcome: queued" in result["errors"]
    assert "outcome must match composition_summary outcome" in result["errors"]


def test_validate_operator_state_requires_composition_summary_dict() -> None:
    operator_state = create_operator_state(composition_summary=make_composition_summary())
    operator_state["composition_summary"] = []

    result = validate_operator_state(operator_state)

    assert result["ok"] is False
    assert "composition_summary must be a dict" in result["errors"]


def test_validate_operator_state_rejects_non_summary_composition_shape() -> None:
    operator_state = create_operator_state(composition_summary=make_composition_summary())
    operator_state["composition_summary"]["decision"]["metadata"] = {"secret": "not allowed"}

    result = validate_operator_state(operator_state)

    assert result["ok"] is False
    assert "composition_summary must match operator flow summary" in result["errors"]


def test_operator_state_exposes_only_public_api() -> None:
    assert state_module.__all__ == [
        "create_operator_state",
        "validate_operator_state",
        "operator_state_to_summary",
    ]


def test_operator_state_uses_only_composition_summary_projection() -> None:
    source = inspect.getsource(state_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    assert "operator_flow_to_summary" in source
    assert all("validate_" not in line for line in import_lines)
    assert all("create_" not in line for line in import_lines)
    assert all("evaluate_" not in line for line in import_lines)
    assert all("compose_" not in line for line in import_lines)


def test_operator_state_avoids_forbidden_imports() -> None:
    source = inspect.getsource(state_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    forbidden_imports = (
        "scheduler",
        "task_runner",
        "operator_loop",
        "persistent_operator",
        "event_log",
        "checkpoint_store",
        "resume",
        "audit_reader",
    )
    for token in forbidden_imports:
        assert all(token not in line for line in import_lines)


def test_operator_state_has_no_runtime_coupling() -> None:
    source = inspect.getsource(state_module)
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
        "transition",
        "lifecycle",
        "ownership",
        "identity",
        "session allocation",
        "allocate_session",
        "operator_session_id",
        "while ",
        "for ",
    )
    for token in forbidden_surface_tokens:
        assert token not in surface


def test_operator_state_has_no_scheduler_coupling() -> None:
    source = inspect.getsource(state_module)

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
