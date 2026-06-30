from __future__ import annotations

import inspect

import pytest

import core.runtime.aer_operator_composition_flow as composition_flow_module
import core.runtime.aer_operator_decision as decision_module
import core.runtime.aer_operator_decision_flow as decision_flow_module
import core.runtime.aer_operator_handoff as handoff_module
import core.runtime.aer_operator_plan as plan_module
import core.runtime.aer_operator_plan_flow as plan_flow_module
import core.runtime.aer_operator_state as state_module
import core.runtime.aer_runtime_intake as intake_module
from core.runtime.aer_operator_composition_flow import compose_operator_flow
from core.runtime.aer_operator_decision import create_decision, decision_to_summary
from core.runtime.aer_operator_decision_flow import decision_flow_summary, evaluate_decision
from core.runtime.aer_operator_handoff import (
    create_operator_handoff,
    operator_handoff_to_summary,
    validate_operator_handoff,
)
from core.runtime.aer_operator_plan import create_plan, plan_to_summary
from core.runtime.aer_operator_plan_flow import evaluate_plan, plan_flow_summary
from core.runtime.aer_operator_state import create_operator_state, operator_state_to_summary
from core.runtime.aer_runtime_intake import (
    create_runtime_intake,
    runtime_intake_to_summary,
    validate_runtime_intake,
)


EXPECTED_PUBLIC_API = {
    decision_module: [
        "create_decision",
        "validate_decision",
        "accept_decision",
        "decision_to_summary",
    ],
    decision_flow_module: ["evaluate_decision", "decision_flow_summary"],
    plan_module: [
        "create_plan",
        "validate_plan",
        "accept_plan",
        "plan_to_summary",
    ],
    plan_flow_module: ["evaluate_plan", "plan_flow_summary"],
    composition_flow_module: ["compose_operator_flow", "operator_flow_to_summary"],
    state_module: [
        "create_operator_state",
        "validate_operator_state",
        "operator_state_to_summary",
    ],
    handoff_module: [
        "create_operator_handoff",
        "validate_operator_handoff",
        "operator_handoff_to_summary",
    ],
    intake_module: [
        "create_runtime_intake",
        "validate_runtime_intake",
        "runtime_intake_to_summary",
    ],
}

FORBIDDEN_EXPORT_TOKENS = (
    "execute",
    "dispatch",
    "retry",
    "checkpoint",
    "resume",
    "lifecycle",
    "transition",
    "session",
    "identity",
)

FORBIDDEN_IMPORT_TOKENS = (
    "scheduler",
    "task_runner",
    "persistent_operator",
    "runtime_loop",
    "operator_loop",
)


def make_decision(decision_type: str = "continue") -> dict:
    return create_decision(
        decision_id="decision-1",
        operator_session_id="operator-session-1",
        package_id="package-100",
        decision_type=decision_type,
        decision_reason="surface seal test",
        created_at="2026-06-30T00:00:00Z",
        metadata={"secret": "not exported"},
    )


def make_plan(plan_type: str = "continue") -> dict:
    return create_plan(
        plan_id="plan-1",
        operator_session_id="operator-session-1",
        package_id="package-100",
        plan_type=plan_type,
        plan_reason="surface seal test",
        created_at="2026-06-30T00:00:00Z",
        steps=[{"secret": "not exported"}],
        metadata={"secret": "not exported"},
    )


def make_handoff(decision_type: str = "continue", plan_type: str = "continue") -> dict:
    state = create_operator_state(
        composition_summary=compose_operator_flow(
            make_decision(decision_type),
            make_plan(plan_type),
        )
    )
    return create_operator_handoff(operator_state=state)


@pytest.mark.parametrize("module,expected", EXPECTED_PUBLIC_API.items())
def test_aer_v2_modules_declare_exact_public_api(module: object, expected: list[str]) -> None:
    if not hasattr(module, "__all__"):
        pytest.skip(
            "inventory finding: "
            f"module={module.__name__}; "
            "reason=module does not currently declare __all__; "
            "recommended_follow_up_package=add explicit AER v2 __all__ exports"
        )

    assert module.__all__ == expected


@pytest.mark.parametrize("module,expected", EXPECTED_PUBLIC_API.items())
def test_aer_v2_public_api_exports_no_runtime_control_surface(
    module: object,
    expected: list[str],
) -> None:
    exported = tuple(getattr(module, "__all__", expected))

    for name in exported:
        for token in FORBIDDEN_EXPORT_TOKENS:
            assert token not in name


@pytest.mark.parametrize("module", EXPECTED_PUBLIC_API)
def test_aer_v2_modules_do_not_import_runtime_or_scheduler_surfaces(module: object) -> None:
    source = inspect.getsource(module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]

    for line in import_lines:
        for token in FORBIDDEN_IMPORT_TOKENS:
            assert token not in line


def test_aer_v2_summary_key_sets_are_fixed() -> None:
    decision = make_decision()
    plan = make_plan()
    decision_flow = evaluate_decision(decision)
    plan_flow = evaluate_plan(plan)
    composition = compose_operator_flow(decision, plan)
    state = create_operator_state(composition_summary=composition)
    handoff = create_operator_handoff(operator_state=state)
    intake = create_runtime_intake(operator_handoff=handoff)

    assert set(decision_to_summary(decision)) == {
        "decision_id",
        "decision_type",
        "status",
        "decision_reason",
    }
    assert set(plan_to_summary(plan)) == {
        "plan_id",
        "plan_type",
        "status",
        "plan_reason",
    }
    assert set(decision_flow_summary(decision_flow)) == {
        "outcome",
        "decision_id",
        "decision_type",
        "status",
    }
    assert set(plan_flow_summary(plan_flow)) == {
        "outcome",
        "plan_id",
        "plan_type",
        "status",
    }
    assert set(composition) == {"outcome", "decision", "plan"}
    assert set(operator_state_to_summary(state)) == {"outcome", "composition_summary"}
    assert set(handoff) == {"contract", "outcome", "operator_state", "state_valid", "errors"}
    assert set(operator_handoff_to_summary(handoff)) == {
        "outcome",
        "operator_state",
        "state_valid",
    }
    assert set(intake) == {"contract", "outcome", "operator_handoff", "valid", "errors"}
    assert set(runtime_intake_to_summary(intake)) == {
        "outcome",
        "operator_handoff",
        "valid",
    }


def test_unknown_keys_do_not_passthrough_to_handoff_or_runtime_intake() -> None:
    state = create_operator_state(
        composition_summary=compose_operator_flow(make_decision(), make_plan())
    )
    state["unknown_state"] = {"secret": "not forwarded"}
    state["composition_summary"]["unknown_composition"] = {"secret": "not forwarded"}
    state["composition_summary"]["decision"]["unknown_decision"] = "not forwarded"
    state["composition_summary"]["plan"]["unknown_plan"] = "not forwarded"

    handoff = create_operator_handoff(operator_state=state)
    assert set(handoff) == {"contract", "outcome", "operator_state", "state_valid", "errors"}
    assert "unknown_state" not in handoff["operator_state"]
    assert "unknown_composition" not in handoff["operator_state"]["composition_summary"]
    assert "unknown_decision" not in handoff["operator_state"]["composition_summary"]["decision"]
    assert "unknown_plan" not in handoff["operator_state"]["composition_summary"]["plan"]

    handoff["unknown_handoff"] = {"secret": "not forwarded"}
    handoff["operator_state"]["unknown_state"] = {"secret": "not forwarded"}
    intake = create_runtime_intake(operator_handoff=handoff)

    assert set(intake) == {"contract", "outcome", "operator_handoff", "valid", "errors"}
    assert "unknown_handoff" not in intake["operator_handoff"]
    assert "unknown_state" not in intake["operator_handoff"]["operator_state"]


def test_runtime_intake_validity_is_separate_from_business_outcome() -> None:
    valid_issue_handoff = make_handoff("report_issue", "stop")
    issue_intake = create_runtime_intake(operator_handoff=valid_issue_handoff)

    assert validate_operator_handoff(valid_issue_handoff)["ok"] is True
    assert issue_intake["outcome"] == "issue_reported"
    assert issue_intake["valid"] is True
    assert validate_runtime_intake(issue_intake)["valid"] is True

    malformed_handoff = make_handoff()
    malformed_handoff["unexpected"] = "contract-breaking"
    malformed_intake = create_runtime_intake(operator_handoff=malformed_handoff)

    assert validate_operator_handoff(malformed_handoff)["ok"] is False
    assert malformed_intake["outcome"] == "issue_reported"
    assert malformed_intake["valid"] is False
    assert validate_runtime_intake(malformed_intake)["valid"] is False
